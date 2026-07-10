#!/usr/bin/env bash
# migrate-state-to-example-orchestration-hub.sh — Idempotent, re-runnable migration script.
#
# Purpose: Migrates ~/.claude working data (state/ + docs/{plans,research,problems}/)
# to the example-orchestration-hub sibling repo, implementing the two-phase cross-repo excision
# contract per cleanup-sweep-hazards.md §10 and the populate-before-repoint
# live-safety sequence from the C6 plan (PM-directed 2026-07-03 re-sequence).
#
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md
# § Phase 2 / C6 / AC5 / § Execution Notes (C6a/C6b split)
#
# Two subcommands:
#
#   --populate (C6a)
#     COPY (do NOT remove) ~/.claude/state/** and
#     ~/.claude/docs/{plans,research,problems}/** → <MAKIMA>/{state,docs}/…
#     Preserves directory structure and file modes (cp -pR, BSD-portable).
#     Idempotent: safe to re-run; existing destination files are overwritten.
#     Originals stay UNTOUCHED.
#
#   --finalize (C6b)
#     1. Delta re-sync: copies any ~/.claude source file NEWER than its example-orchestration-hub
#        counterpart (capturing writes that happened after --populate).
#     2. Per-path guard: before removing ANY source file, confirms the example-orchestration-hub
#        destination copy exists. Fails loud on any missing destination.
#     3. Removes ~/.claude originals for both source trees.
#     DO NOT RUN until after: C3/C4/C12 repoint + C11 dogfood consistency gate.
#
# Cross-platform: bash ≥4 + BSD coreutils. No GNU-isms (no sed -i, grep -P,
# date -d, date %N, realpath). Safe to re-run multiple times.
#
# Usage:
#   bash migrate-state-to-example-orchestration-hub.sh --populate
#   bash migrate-state-to-example-orchestration-hub.sh --finalize   # only after dogfood gate
#
# Environment overrides:
#   EXAMPLE_ORCHESTRATION_HUB_ROOT  — override the example-orchestration-hub repo path (skips machine-local lookup).
#   CLAUDE_HOME  — override the ~/.claude meta-repo path.

# ---------------------------------------------------------------------------
# Bash ≥4 guard (uses [[ and local — reachable on bash 3.2 syntax, but the
# explicit version check gives a clear remediation message).
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  echo "ERROR: migrate-state-to-example-orchestration-hub.sh requires bash ≥ 4." >&2
  echo "  macOS ships bash 3.2 — install with: brew install bash" >&2
  echo "  Then invoke with: /usr/local/bin/bash migrate-state-to-example-orchestration-hub.sh $*" >&2
  exit 1
fi

set -euo pipefail

# ---------------------------------------------------------------------------
# Locate the coordinator plugin root and source the EXAMPLE_ORCHESTRATION_HUB_ROOT resolver.
# The script lives in <plugin-root>/bin/, so lib is one level up.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LIB_RESOLVER="${PLUGIN_ROOT}/lib/coordinator-example-orchestration-hub-root.sh"

if [[ ! -f "${LIB_RESOLVER}" ]]; then
  echo "ERROR: cannot find coordinator-example-orchestration-hub-root.sh at: ${LIB_RESOLVER}" >&2
  echo "  Is this script in <plugin-root>/bin/? Check your plugin structure." >&2
  exit 1
fi

# shellcheck source=../lib/coordinator-example-orchestration-hub-root.sh
source "${LIB_RESOLVER}"

# ---------------------------------------------------------------------------
# Resolve CLAUDE_HOME (meta-repo source)
# ---------------------------------------------------------------------------
CLAUDE_HOME="${CLAUDE_HOME:-${HOME}/.claude}"
if [[ ! -d "${CLAUDE_HOME}" ]]; then
  echo "ERROR: CLAUDE_HOME not found at: ${CLAUDE_HOME}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve EXAMPLE_ORCHESTRATION_HUB_ROOT (destination repo)
# ---------------------------------------------------------------------------
EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED=$(coordinator_example_orchestration_hub_root) || {
  echo "ERROR: cannot resolve example-orchestration-hub root. See remediation above." >&2
  exit 1
}
# Normalise trailing slash and export
EXAMPLE_ORCHESTRATION_HUB_ROOT="${EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED%/}"

# ---------------------------------------------------------------------------
# Source trees (relative to CLAUDE_HOME) and their destination trees
# ---------------------------------------------------------------------------
# Array of "source:dest" pairs relative to CLAUDE_HOME / EXAMPLE_ORCHESTRATION_HUB_ROOT.
# Each source dir is mirrored into the matching dest dir inside example-orchestration-hub.
declare -a TREE_PAIRS=(
  "state:state"
  "archive:archive"
  "docs/plans:docs/plans"
  "docs/research:docs/research"
  "docs/problems:docs/problems"
)

# ---------------------------------------------------------------------------
# copy_tree SRC_DIR DEST_DIR
#
# Copies all files from SRC_DIR into DEST_DIR, preserving structure and modes.
# Uses `find -type f` (not grep --include) per migration-script-conventions.md §1.
# cp -pR is BSD-portable (preserve perms/times, recurse, no GNU-isms).
# Idempotent: existing destination files are simply overwritten.
# ---------------------------------------------------------------------------
copy_tree() {
  local src="$1"
  local dst="$2"

  if [[ ! -d "${src}" ]]; then
    echo "  SKIP (source absent): ${src}"
    return 0
  fi

  # Ensure destination directory exists
  mkdir -p "${dst}"

  local file_count=0
  local skip_count=0

  # find -type f enumerates ALL files regardless of extension, per conventions §1.
  while IFS= read -r src_file; do
    # Compute relative path from src root, then destination path.
    local rel="${src_file#${src}/}"
    local dst_file="${dst}/${rel}"

    # Ensure parent directory exists in destination.
    local dst_parent="${dst_file%/*}"
    if [[ "${dst_parent}" != "${dst_file}" ]]; then
      mkdir -p "${dst_parent}"
    fi

    # cp -pR: -p preserve modes/timestamps/owner, -R recursive (for single files: no-op for -R).
    # Using -p only for files since -R on a single file doesn't make sense but is harmless.
    if cp -p "${src_file}" "${dst_file}"; then
      (( file_count++ )) || true
    else
      echo "  WARN: failed to copy: ${src_file}" >&2
      (( skip_count++ )) || true
    fi
  done < <(find "${src}" -type f)

  echo "  Copied ${file_count} files from ${src} → ${dst} (${skip_count} failed)"
}

# ---------------------------------------------------------------------------
# --populate subcommand (C6a)
# COPY source trees to example-orchestration-hub. Do NOT remove originals.
# ---------------------------------------------------------------------------
cmd_populate() {
  echo "=== migrate-state-to-example-orchestration-hub --populate (C6a) ==="
  echo "  Source (CLAUDE_HOME): ${CLAUDE_HOME}"
  echo "  Destination (EXAMPLE_ORCHESTRATION_HUB_ROOT): ${EXAMPLE_ORCHESTRATION_HUB_ROOT}"
  echo ""

  local total_files=0
  local pair

  for pair in "${TREE_PAIRS[@]}"; do
    local src_rel="${pair%%:*}"
    local dst_rel="${pair##*:}"
    local src="${CLAUDE_HOME}/${src_rel}"
    local dst="${EXAMPLE_ORCHESTRATION_HUB_ROOT}/${dst_rel}"

    echo "[populate] ${src_rel} → ${dst_rel}"
    copy_tree "${src}" "${dst}"
    echo ""
  done

  echo "=== populate complete — originals UNTOUCHED in ${CLAUDE_HOME} ==="
  echo "    Next: run C3/C4/C12 repoint, then C11 dogfood gate, then --finalize"
}

# ---------------------------------------------------------------------------
# --finalize subcommand (C6b)
# 1. Delta re-sync (copy files newer in source than destination)
# 2. Per-path guard: confirm example-orchestration-hub dest exists before any rm
# 3. Remove source originals
#
# Two-phase cross-repo excision per cleanup-sweep-hazards.md §10:
#   Phase 1 (--populate) already ran and populated the destination.
#   Phase 2 (this step): verify destination, then remove source.
# ---------------------------------------------------------------------------
cmd_finalize() {
  echo "=== migrate-state-to-example-orchestration-hub --finalize (C6b) ==="
  echo "  Source (CLAUDE_HOME): ${CLAUDE_HOME}"
  echo "  Destination (EXAMPLE_ORCHESTRATION_HUB_ROOT): ${EXAMPLE_ORCHESTRATION_HUB_ROOT}"
  echo ""

  # -----------------------------------------------------------------------
  # Step 1: Delta re-sync — copy any source file NEWER than its example-orchestration-hub copy.
  # (Captures writes that happened between --populate and now.)
  # -----------------------------------------------------------------------
  echo "--- Step 1: Delta re-sync ---"

  local pair
  for pair in "${TREE_PAIRS[@]}"; do
    local src_rel="${pair%%:*}"
    local dst_rel="${pair##*:}"
    local src="${CLAUDE_HOME}/${src_rel}"
    local dst="${EXAMPLE_ORCHESTRATION_HUB_ROOT}/${dst_rel}"

    if [[ ! -d "${src}" ]]; then
      echo "  SKIP (source absent): ${src}"
      continue
    fi

    echo "[delta] ${src_rel} → ${dst_rel}"
    local delta_count=0

    while IFS= read -r src_file; do
      local rel="${src_file#${src}/}"
      local dst_file="${dst}/${rel}"
      local dst_parent="${dst_file%/*}"

      # Check if source is newer than destination (or destination doesn't exist).
      # BSD `test -nt` (newer-than) is portable and available on macOS.
      if [[ "${src_file}" -nt "${dst_file}" ]] || [[ ! -f "${dst_file}" ]]; then
        mkdir -p "${dst_parent}"
        if cp -p "${src_file}" "${dst_file}"; then
          (( delta_count++ )) || true
        else
          echo "  WARN: delta copy failed: ${src_file}" >&2
        fi
      fi
    done < <(find "${src}" -type f)

    echo "  Delta-synced ${delta_count} files from ${src}"
    echo ""
  done

  # -----------------------------------------------------------------------
  # Step 2: Per-path guard — verify EVERY source file is confirmed in example-orchestration-hub
  # before removing ANYTHING. Fail loud on any missing destination.
  # cleanup-sweep-hazards.md §10: producer-side removal MUST verify example-orchestration-hub-side
  # population first, per-path, before any rm.
  # -----------------------------------------------------------------------
  echo "--- Step 2: Pre-removal verification guard ---"

  local missing_count=0

  for pair in "${TREE_PAIRS[@]}"; do
    local src_rel="${pair%%:*}"
    local dst_rel="${pair##*:}"
    local src="${CLAUDE_HOME}/${src_rel}"
    local dst="${EXAMPLE_ORCHESTRATION_HUB_ROOT}/${dst_rel}"

    if [[ ! -d "${src}" ]]; then
      continue
    fi

    while IFS= read -r src_file; do
      local rel="${src_file#${src}/}"
      local dst_file="${dst}/${rel}"

      if [[ ! -f "${dst_file}" ]]; then
        echo "  GUARD FAIL: example-orchestration-hub copy missing for: ${src_file}" >&2
        echo "             expected at: ${dst_file}" >&2
        (( missing_count++ )) || true
      fi
    done < <(find "${src}" -type f)
  done

  if [[ "${missing_count}" -gt 0 ]]; then
    echo "" >&2
    echo "ERROR: ${missing_count} source file(s) have no confirmed example-orchestration-hub copy." >&2
    echo "  Aborting --finalize. Run --populate again to re-sync missing files," >&2
    echo "  then retry --finalize." >&2
    exit 1
  fi

  echo "  Guard PASSED: all source files confirmed present in example-orchestration-hub."
  echo ""

  # -----------------------------------------------------------------------
  # Step 3: Remove source originals from ~/.claude
  # Removes files first, then cleans up empty directories.
  # Per migration-script-conventions.md §2: rmdir empty source dirs before
  # any git mv; here we clean up after removing files.
  # -----------------------------------------------------------------------
  echo "--- Step 3: Remove source originals ---"

  for pair in "${TREE_PAIRS[@]}"; do
    local src_rel="${pair%%:*}"
    local src="${CLAUDE_HOME}/${src_rel}"

    if [[ ! -d "${src}" ]]; then
      echo "  SKIP (source absent): ${src}"
      continue
    fi

    echo "[remove] ${src_rel}"
    local remove_count=0

    while IFS= read -r src_file; do
      if rm -f "${src_file}"; then
        (( remove_count++ )) || true
      else
        echo "  WARN: failed to remove: ${src_file}" >&2
      fi
    done < <(find "${src}" -type f)

    echo "  Removed ${remove_count} files from ${src}"

    # Clean up empty directories left behind (depth-first via find -depth).
    # Per migration-script-conventions.md §2: explicitly remove empty dirs.
    find "${src}" -type d -empty -delete 2>/dev/null || true
    echo "  Cleaned empty directories under ${src}"
    echo ""
  done

  echo "=== finalize complete ==="
  echo "    Source trees removed from ${CLAUDE_HOME}."
  echo "    Working data now lives in ${EXAMPLE_ORCHESTRATION_HUB_ROOT}."
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
if [[ $# -eq 0 ]]; then
  echo "Usage: migrate-state-to-example-orchestration-hub.sh --populate | --finalize" >&2
  echo "" >&2
  echo "  --populate   Copy ~/.claude working data to example-orchestration-hub (C6a)." >&2
  echo "               Safe to re-run. Originals stay untouched." >&2
  echo "  --finalize   Delta re-sync + remove ~/.claude originals (C6b)." >&2
  echo "               Run ONLY after: C3/C4/C12 repoint + C11 dogfood gate." >&2
  exit 1
fi

case "$1" in
  --populate)
    cmd_populate
    ;;
  --finalize)
    cmd_finalize
    ;;
  *)
    echo "ERROR: unknown subcommand: $1" >&2
    echo "Usage: migrate-state-to-example-orchestration-hub.sh --populate | --finalize" >&2
    exit 1
    ;;
esac
