#!/usr/bin/env bash
# coordinator-complete-entry.sh — Scaffold a pre-filled workstream completion entry.
#
# Purpose: consolidates the mechanical spine of /workstream-complete Step 2.6
# (completion-entry ladder) into one command that emits a pre-filled entry with
# up to two model-residue placeholders:
#   <!-- NATURE-INFER -->  — present only when --nature is omitted
#   <!-- PROSE: ... -->    — always present (title + body slot for the model)
#
# Spec backlink: docs/plans/2026-07-06-cockpit-contract-v27 (§ coordinator-complete-entry)
#
# Wraps (NEVER reimplements):
#   migrate-completion-log-legacy.sh  — step 2.6.2: idempotent monolith → legacy/ move
#   coordinator-session-loe.sh        — step 2.6.5a: single-session LoE
#   aggregate-chain-loe.sh            — step 2.6.5a: chain-terminal LoE
#
# Usage:
#   coordinator-complete-entry.sh \
#       --sid <WSC_SID> \
#       --disposition <single-session|chain-terminal> \
#       [--consumed-handoff <path>]         required when chain-terminal
#       [--governing-plan-slug <slug>]      drives idempotency guard + chain-slug filename
#       [--nature <roadmap|bugfix|tech-debt|infra>]
#
# Exit codes:
#   0  — entry written, OR idempotent no-op (entry already exists for this chain slug)
#   1  — argument error (missing required flag, invalid --nature enum value, etc.)
#   2  — environment error (not inside a git repository)
#
# Negative-spec — commits: field:
#   This CLI NEVER seeds the commits: list. Step 2.6.8 owns that field entirely
#   via reconcile-completion-commits.sh --append (Session-Id-trailer reconcile).
#
# BSD-portable bash >=4; no GNU-isms (no grep --include, no date -d, etc.).

set -euo pipefail

# ---------------------------------------------------------------------------
# bash >=4 guard — must parse cleanly on bash 3.2 (no bash-4 syntax in this block)
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "coordinator-complete-entry.sh: requires bash >= 4 (current: ${BASH_VERSION:-?})" >&2
  echo "  Install via Homebrew: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Sibling-script resolution — derived from BASH_SOURCE[0]; never hardcoded.
# This CLI lives in coordinator/bin/; siblings resolve relative to it regardless
# of the caller's CWD (callers may cd into a fixture or target repo before invocation).
# ---------------------------------------------------------------------------
_CC_BIN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Closed enum for --nature (authority: coordinator/docs/wiki/completion-log-release-loop.md)
# ---------------------------------------------------------------------------
_VALID_NATURES=("roadmap" "bugfix" "tech-debt" "infra")

# ---------------------------------------------------------------------------
# usage()
# ---------------------------------------------------------------------------
usage() {
  cat <<'USAGE'
Usage: coordinator-complete-entry.sh --sid <SID> --disposition <disp> [OPTIONS]

Required:
  --sid <WSC_SID>
      Session ID; last 6 characters become sid6 in the output filename.
  --disposition <single-session|chain-terminal>
      Single-session: one-session workstream.
      Chain-terminal: consuming and closing a multi-session handoff chain.

Options:
  --consumed-handoff <path>
      Path to the consumed terminal handoff file.
      Required when --disposition chain-terminal.
  --governing-plan-slug <slug>
      Plan slug driving this workstream (e.g. "2026-07-06-my-plan").
      When supplied: drives idempotency guard AND chain-slug in the filename.
      When omitted: filename uses "adhoc" segment.
  --nature <roadmap|bugfix|tech-debt|infra>
      Work category for the completion entry.
      When omitted: a <!-- NATURE-INFER --> residue placeholder is left in the file.
  --help
      Show this message.

Exit codes:
  0  entry written, or idempotent no-op (entry already exists for this chain slug)
  1  argument error
  2  environment error (not in a git repo)
USAGE
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
SID=""
DISPOSITION=""
CONSUMED_HANDOFF=""
GOVERNING_PLAN_SLUG=""
NATURE_VAL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sid)
      [[ -n "${2:-}" ]] || { echo "ERROR: --sid requires a value" >&2; exit 1; }
      SID="$2"; shift 2 ;;
    --disposition)
      [[ -n "${2:-}" ]] || { echo "ERROR: --disposition requires a value" >&2; exit 1; }
      DISPOSITION="$2"; shift 2 ;;
    --consumed-handoff)
      [[ -n "${2:-}" ]] || { echo "ERROR: --consumed-handoff requires a value" >&2; exit 1; }
      CONSUMED_HANDOFF="$2"; shift 2 ;;
    --governing-plan-slug)
      [[ -n "${2:-}" ]] || { echo "ERROR: --governing-plan-slug requires a value" >&2; exit 1; }
      # Review: code-reviewer — reject path traversal and regex injection at parse time;
      # allows date-prefixed slugs (e.g. 2026-07-01_164217_wsc-step-2.6-chain) while
      # blocking /, \, .., and leading-dot traversal.
      if ! [[ "$2" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || [[ "$2" == *".."* ]]; then
        echo "ERROR: --governing-plan-slug contains invalid characters: '$2'" >&2
        exit 1
      fi
      GOVERNING_PLAN_SLUG="$2"; shift 2 ;;
    --nature)
      [[ -n "${2:-}" ]] || { echo "ERROR: --nature requires a value" >&2; exit 1; }
      NATURE_VAL="$2"; shift 2 ;;
    --help|-h)
      usage; exit 0 ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Validate required flags
# ---------------------------------------------------------------------------
if [[ -z "$SID" ]]; then
  echo "ERROR: --sid is required" >&2; usage >&2; exit 1
fi
if [[ -z "$DISPOSITION" ]]; then
  echo "ERROR: --disposition is required" >&2; usage >&2; exit 1
fi
case "$DISPOSITION" in
  single-session|chain-terminal) ;;
  *)
    echo "ERROR: --disposition must be 'single-session' or 'chain-terminal'; got: '${DISPOSITION}'" >&2
    exit 1 ;;
esac
if [[ "$DISPOSITION" == "chain-terminal" && -z "$CONSUMED_HANDOFF" ]]; then
  echo "ERROR: --consumed-handoff is required when --disposition chain-terminal" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Validate --nature against the closed enum (fail-loud; names all four valid values)
# ---------------------------------------------------------------------------
if [[ -n "$NATURE_VAL" ]]; then
  _nature_ok=false
  for _v in "${_VALID_NATURES[@]}"; do
    [[ "$NATURE_VAL" == "$_v" ]] && { _nature_ok=true; break; }
  done
  if ! $_nature_ok; then
    echo "ERROR: --nature '${NATURE_VAL}' is not a valid completion nature." >&2
    echo "Valid values: roadmap | bugfix | tech-debt | infra" >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Resolve repo root (required for all file operations)
# ---------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERROR: not inside a git repository. Run from within the target repo." >&2
  exit 2
}

COMPLETED_DIR="${REPO_ROOT}/archive/completed"
YYYYMM="$(date +%Y-%m)"
YYYYMMDD="$(date +%Y-%m-%d)"

# ---------------------------------------------------------------------------
# Step 2.6.2 — Legacy monolith migrate
# Invoke migrate-completion-log-legacy.sh when a root YYYY-MM.md exists and
# COORDINATOR_OVERRIDE_LEGACY_MONOLITH is unset.
# DO NOT hand-roll git mv here — the migrate helper is the tripwire-excepted
# canonical path; reimplementing it triggers check-no-monolith-completion-append.sh.
# ---------------------------------------------------------------------------
_MONOLITH="${COMPLETED_DIR}/${YYYYMM}.md"
if [[ -z "${COORDINATOR_OVERRIDE_LEGACY_MONOLITH:-}" ]] && [[ -f "$_MONOLITH" ]]; then
  bash "${_CC_BIN}/migrate-completion-log-legacy.sh" --root "$REPO_ROOT"
fi

# ---------------------------------------------------------------------------
# Step 2.6.3 — Chain-slug ladder
# Ladder: --governing-plan-slug → (future: handoff stem / workstream slug) → null (adhoc)
# ---------------------------------------------------------------------------
CHAIN_SLUG="${GOVERNING_PLAN_SLUG:-}"

# ---------------------------------------------------------------------------
# Step 2.6.3a — Idempotency guard
# When a governing-plan-slug is set, scan archive/completed/ (excluding legacy/)
# for any existing entry whose chain: field matches. If found, exit 0 (no-op).
# Primary: query-records.sh --type completion --where chain=<slug> (degrade gracefully
# on absence or non-zero). Fallback: grep-based scan (BSD-portable).
# ---------------------------------------------------------------------------
if [[ -n "$CHAIN_SLUG" ]] && [[ -d "$COMPLETED_DIR" ]]; then
  _found_existing=false
  _existing_path=""

  # Resolve the concrete pre-existing entry path via a BSD-portable grep scan.
  # query-records signals existence; the scan gives us the actual path to echo on no-op
  # (contract: stdout is ALWAYS the entry path — write-or-no-op — so the caller's
  # entry_path=$(...) capture is usable either way).
  while IFS= read -r _f; do
    [[ -f "$_f" ]] || continue
    [[ "$_f" == */legacy/* ]] && continue
    # Review: code-reviewer (F7) — literal match on the quoted YAML value as written;
    # avoids regex metacharacter mismatches when CHAIN_SLUG contains '.' or '-'.
    if grep -qF "chain: \"${CHAIN_SLUG}\"" "$_f" 2>/dev/null; then
      _existing_path="$_f"
      break
    fi
  done < <(find "$COMPLETED_DIR" -maxdepth 2 -name "*.md" 2>/dev/null || true)

  # Primary existence signal: query-records.sh (degrade to the grep result on absence).
  if [[ -x "${_CC_BIN}/query-records.sh" ]]; then
    _qr_rc=0
    _qr_out=""
    _qr_out="$(bash "${_CC_BIN}/query-records.sh" \
      --type completion --where "chain=${CHAIN_SLUG}" 2>/dev/null)" || _qr_rc=$?
    [[ $_qr_rc -eq 0 ]] && [[ -n "$_qr_out" ]] && _found_existing=true
  fi
  [[ -n "$_existing_path" ]] && _found_existing=true

  if $_found_existing; then
    # Review: code-reviewer (F1) — recover path from _qr_out when grep scan missed it
    # (file beyond maxdepth 2, chain: field format mismatch, or grep error).
    if [[ -z "$_existing_path" ]] && [[ -n "$_qr_out" ]] && [[ -f "$_qr_out" ]]; then
      _existing_path="$_qr_out"
    fi
    # Fail loud if existence was signaled but path is still unrecoverable.
    # Never emit silent empty stdout — callers do entry_path=$(...) and rely on the value.
    if [[ -z "$_existing_path" ]]; then
      echo "ERROR: existing entry detected for chain '${CHAIN_SLUG}' but path unrecoverable" >&2
      exit 1
    fi
    # stdout carries the pre-existing entry path; the stand-down note goes to stderr.
    echo "$_existing_path"
    echo "stand-down: completion entry already exists for chain '${CHAIN_SLUG}' — no duplicate written" >&2
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# Step 2.6.5a — LoE block
# single-session  → coordinator-session-loe.sh --format yaml-frontmatter
# chain-terminal  → aggregate-chain-loe.sh --terminal-handoff <path> --format yaml-frontmatter
# Degrade to null block on absence or non-zero exit (these helpers require live
# session state that may be absent in CI / fixture contexts).
# ---------------------------------------------------------------------------
_LOE_BLOCK=""
_loe_rc=0

if [[ "$DISPOSITION" == "single-session" ]]; then
  if [[ -x "${_CC_BIN}/coordinator-session-loe.sh" ]]; then
    _LOE_BLOCK="$(bash "${_CC_BIN}/coordinator-session-loe.sh" \
      --format yaml-frontmatter 2>/dev/null)" || _loe_rc=$?
  fi
elif [[ "$DISPOSITION" == "chain-terminal" ]] && [[ -n "$CONSUMED_HANDOFF" ]]; then
  if [[ -x "${_CC_BIN}/aggregate-chain-loe.sh" ]]; then
    _LOE_BLOCK="$(bash "${_CC_BIN}/aggregate-chain-loe.sh" \
      --terminal-handoff "$CONSUMED_HANDOFF" \
      --format yaml-frontmatter 2>/dev/null)" || _loe_rc=$?
  fi
fi

# Degrade to null block on any loe failure or empty output
if [[ -z "$_LOE_BLOCK" ]] || [[ $_loe_rc -ne 0 ]]; then
  _LOE_BLOCK="loe:
  agent_dispatches: null
  opus_dispatches: null
  em_tokens: null
  tshirt: null"
fi

# ---------------------------------------------------------------------------
# Step 2.6.6 — Build output path and write entry
# Filename: YYYY-MM-DD-<chain-slug>-<sid6>.md  (or ...-adhoc-<sid6>.md when null chain)
# ---------------------------------------------------------------------------
SID6="${SID: -6}"

if [[ -n "$CHAIN_SLUG" ]]; then
  _ENTRY_FILENAME="${YYYYMMDD}-${CHAIN_SLUG}-${SID6}.md"
else
  _ENTRY_FILENAME="${YYYYMMDD}-adhoc-${SID6}.md"
fi

_ENTRY_DIR="${COMPLETED_DIR}/${YYYYMM}"
_ENTRY_PATH="${_ENTRY_DIR}/${_ENTRY_FILENAME}"

mkdir -p "$_ENTRY_DIR"

# chain_terminal field mirrors --disposition
_CHAIN_TERMINAL="false"
[[ "$DISPOSITION" == "chain-terminal" ]] && _CHAIN_TERMINAL="true"

# ---------------------------------------------------------------------------
# Rollup-sentence resolution (AC4)
# When the governing plan carries deliverable_id: in its frontmatter, call
# coordinator-render-rollup.sh and capture the rendered "advances" sentence.
# Fail-open (contract §4.2): any guard miss → _ROLLUP_SENTENCE stays empty,
# entry composes exactly as before.  Render failure NEVER aborts the write.
# ---------------------------------------------------------------------------
_ROLLUP_SENTENCE=""
if [[ -n "$GOVERNING_PLAN_SLUG" ]]; then
  _PLAN_FILE="${REPO_ROOT}/docs/plans/${GOVERNING_PLAN_SLUG}.md"
  if [[ -f "$_PLAN_FILE" ]]; then
    _raw_dlv_line="$(grep -m1 '^deliverable_id:' "$_PLAN_FILE" 2>/dev/null || true)"
    if [[ -n "$_raw_dlv_line" ]]; then
      _DLV_ID="${_raw_dlv_line#deliverable_id:}"
      # Trim leading/trailing whitespace (BSD-portable via printf+sed).
      # Review: code-reviewer — F4: merged two sequential sed calls into one invocation (fewer subprocesses).
      _DLV_ID="$(printf '%s' "$_DLV_ID" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
      # Strip surrounding double-quotes if present.
      _DLV_ID="${_DLV_ID#\"}"; _DLV_ID="${_DLV_ID%\"}"
      # Strip surrounding single-quotes if present (symmetric; guards YAML single-quoted strings).
      # Review: code-reviewer — F5: added single-quote stripping to match double-quote strip above.
      _DLV_ID="${_DLV_ID#\'}"; _DLV_ID="${_DLV_ID%\'}"
      if [[ -n "$_DLV_ID" ]]; then
        # Resolve render helper: PATH-first (enables test shims), then sibling.
        _RENDER_HELPER=""
        if command -v coordinator-render-rollup.sh >/dev/null 2>&1; then
          _RENDER_HELPER="$(command -v coordinator-render-rollup.sh)"
        elif [[ -x "${_CC_BIN}/coordinator-render-rollup.sh" ]]; then
          _RENDER_HELPER="${_CC_BIN}/coordinator-render-rollup.sh"
        fi
        if [[ -n "$_RENDER_HELPER" ]]; then
          _ROLLUP_SENTENCE="$(bash "$_RENDER_HELPER" "$_DLV_ID" "$REPO_ROOT" 2>/dev/null || true)"
        fi
      fi
    fi
  fi
fi

# Write the completion entry.
# Negative-spec: commits: is left as [] — Step 2.6.8 owns this field exclusively.
{
  echo "---"
  echo "title: \"PLACEHOLDER — replace with past-tense workstream title\""
  echo "created: ${YYYYMMDD}"
  if [[ -n "$NATURE_VAL" ]]; then
    echo "nature: ${NATURE_VAL}"
    echo "nature_inferred: false"
  else
    echo "nature: null"
    echo "nature_inferred: true"
  fi
  if [[ -n "$CHAIN_SLUG" ]]; then
    echo "chain: \"${CHAIN_SLUG}\""
  fi
  echo "commits: []"
  echo "status: pending-release"
  echo "chain_terminal: ${_CHAIN_TERMINAL}"
  echo "authored_by: \"${SID}\""
  echo "${_LOE_BLOCK}"
  echo "---"
  echo ""
  echo "<!-- PROSE: Replace this with a ≤8-sentence past-tense description of what shipped and why it matters. -->"
  if [[ -n "$_ROLLUP_SENTENCE" ]]; then
    echo ""
    # Review: code-reviewer — F7: printf guards against leading-dash args mis-parsed as echo flags.
    printf '%s\n' "$_ROLLUP_SENTENCE"
  fi
  if [[ -z "$NATURE_VAL" ]]; then
    echo ""
    echo "<!-- NATURE-INFER: Set the nature: field above (roadmap | bugfix | tech-debt | infra) and remove this comment. -->"
  fi
} > "$_ENTRY_PATH"

# ---------------------------------------------------------------------------
# Output: path to stdout + one-line residue summary
# ---------------------------------------------------------------------------
# stdout carries ONLY the entry path — callers do `entry_path=$(coordinator-complete-entry.sh …)`
# and a polluted stdout breaks that capture. The residue summary is human-facing → stderr.
echo "$_ENTRY_PATH"
if [[ -z "$NATURE_VAL" ]]; then
  echo "Residue: nature (<!-- NATURE-INFER -->), prose (<!-- PROSE: ... -->)" >&2
else
  echo "Residue: prose (<!-- PROSE: ... -->)" >&2
fi
