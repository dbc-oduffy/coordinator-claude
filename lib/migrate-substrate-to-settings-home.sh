#!/usr/bin/env bash
# migrate-substrate-to-settings-home.sh — one-time idempotent migration helper.
#
# Copies legacy ~/.claude/{machine-local/,settings-manifest.md} into the
# coordinator settings home (<settings-home>/) and installs a compat realpath-
# symlink at ~/.claude/machine-local pointing to <settings-home>/machine-local.
#
# setup/ is intentionally NOT migrated: nothing reads setup/ from settings-home
# at runtime (coordinator continues to read ~/.claude/setup/), and the percolation
# step in install-substrate.sh writes the canonical copy there. Migrating setup/
# would create two diverging locations that the fail-loud divergent-file guard then
# blocks on every re-run.
#
# This migration MUST be the first machine-local action in install-substrate.sh —
# before mkdir-p or copy-if-absent seeding — so operator-provisioned files
# (registry.local.toml carrying repos.*/ plugin.mirrors.*) are not orphaned by
# the fresh-template seed that runs after.
#
# Usage:
#   bash migrate-substrate-to-settings-home.sh [--dry-run]
#
# Per-file guards:
#   source-present AND destination-file-absent   → copy
#   both-present AND identical content           → no-op (already migrated)
#   both-present AND divergent content           → FAIL LOUD (exit 1)
#   source-absent                                → no-op (skip)
#
# Idempotent: once the compat symlink is in place at ~/.claude/machine-local,
# re-running is a clean no-op (the legacy-dir guard is a real-dir check).
#
# Compat symlink:
#   After all files are verified or migrated, ~/.claude/machine-local (the legacy
#   real directory) is replaced with a symlink pointing to <settings-home>/machine-local.
#   Three direct-binding consumers (example-game-repo, project-rag, project-rag-ue-addon) read
#   TOML files from that path; the symlink lets them resolve the relocated content
#   unchanged through the compat window.
#   The symlink is NOT removed here — removal is the phase-2 gated tail.
#
# Sources: coordinator/lib/settings-home.sh (the C1 settings-home seam).
#
# Portability: bash >=3.2 + BSD coreutils (stock macOS). No GNU-only flags.
# python3 (coordinator hard dep) used for portable realpath resolution.
#
# Spec backlink: docs/plans/2026-07-06-durable-substrate-to-settings-home.md § C3
# RAG-bait: coordinator substrate migration; settings-home relocation; compat symlink

set -euo pipefail

# ---------------------------------------------------------------------------
# Script location + lib sourcing
# ---------------------------------------------------------------------------

if [[ -z "${BASH_SOURCE[0]:-}" ]] || [[ ! -f "${BASH_SOURCE[0]}" ]]; then
    echo "migrate-substrate-to-settings-home: cannot derive script location (BASH_SOURCE[0] empty or not a real file)" >&2
    exit 1
fi
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_SH_LIB="${_SCRIPT_DIR}/settings-home.sh"
if [[ ! -f "$_SH_LIB" ]]; then
    echo "migrate-substrate-to-settings-home: settings-home.sh not found at ${_SH_LIB}" >&2
    echo "  The C1 settings-home seam must be landed before running this migration." >&2
    exit 1
fi
source "$_SH_LIB"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

_DRY_RUN=0
for _arg in "$@"; do
    case "$_arg" in
        --dry-run) _DRY_RUN=1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_CLAUDE_BASE="${CLAUDE_HOME:-${HOME}}/.claude"
_SETTINGS_HOME="$(_coordinator_settings_home)"

_LEGACY_ML="${_CLAUDE_BASE}/machine-local"
_LEGACY_MANIFEST="${_CLAUDE_BASE}/settings-manifest.md"

_DST_ML="${_SETTINGS_HOME}/machine-local"
_DST_MANIFEST="${_SETTINGS_HOME}/settings-manifest.md"

# ---------------------------------------------------------------------------
# Per-file copy helper: source-present + dest-absent → copy;
#                       both-present + identical → no-op;
#                       both-present + divergent → FAIL LOUD.
# Returns 1 on divergent content (caller should propagate with || return 1).
# ---------------------------------------------------------------------------

_copy_one_file() {
    local _src="$1" _dst="$2"

    # Source absent: skip (no-op).
    [[ -f "$_src" ]] || return 0

    if [[ ! -f "$_dst" ]]; then
        # Destination absent: create parent dir and copy.
        if [[ "$_DRY_RUN" -eq 1 ]]; then
            echo "[migrate] DRY-RUN: would copy ${_src} → ${_dst}"
        else
            mkdir -p "$(dirname "$_dst")"
            cp -p "$_src" "$_dst"
            echo "[migrate] copied ${_src} → ${_dst}"
        fi
        return 0
    fi

    # Both present: content comparison.
    if diff -q "$_src" "$_dst" >/dev/null 2>&1; then
        # Identical: already migrated, no-op.
        return 0
    else
        # Divergent: FAIL LOUD. Operator must reconcile manually.
        echo "migrate-substrate-to-settings-home: DIVERGENT FILE — cannot safely migrate." >&2
        echo "  Source : ${_src}" >&2
        echo "  Dest   : ${_dst}" >&2
        echo "  Both files exist and have different content." >&2
        echo "  Remediation: manually reconcile the two files, then re-run the migration." >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Tree migration helper: enumerate with find (not shell glob — dotfiles +
# empty-dir edge cases). Copies all regular files then creates empty subdirs.
# ---------------------------------------------------------------------------

_migrate_tree() {
    local _src_dir="$1" _dst_dir="$2"

    [[ -d "$_src_dir" ]] || return 0

    # Migrate all regular files (find includes dotfiles by default).
    # Process substitution < <(...) is bash 3.2+ compatible.
    local _rel _src_f _dst_f
    while IFS= read -r _rel; do
        _src_f="${_src_dir}/${_rel}"
        _dst_f="${_dst_dir}/${_rel}"
        _copy_one_file "$_src_f" "$_dst_f" || return 1
    done < <(cd "$_src_dir" && find . -type f | sed 's|^\./||')

    # Create any empty subdirectories that find -type f would silently skip.
    local _dst_sub
    while IFS= read -r _rel; do
        _dst_sub="${_dst_dir}/${_rel}"
        if [[ ! -d "$_dst_sub" ]]; then
            if [[ "$_DRY_RUN" -eq 1 ]]; then
                echo "[migrate] DRY-RUN: would create empty subdir ${_dst_sub}"
            else
                mkdir -p "$_dst_sub"
                echo "[migrate] created empty subdir ${_dst_sub}"
            fi
        fi
    done < <(cd "$_src_dir" && find . -mindepth 1 -type d -empty 2>/dev/null | sed 's|^\./||')

    return 0
}

# ---------------------------------------------------------------------------
# Main migration
# ---------------------------------------------------------------------------

_any_work=0

# 1. machine-local/
# Guard: real directory (not already a symlink = already migrated from a prior run).
if [[ -d "$_LEGACY_ML" ]] && [[ ! -L "$_LEGACY_ML" ]]; then
    _migrate_tree "$_LEGACY_ML" "$_DST_ML" || exit 1
    _any_work=1
fi

# setup/ is NOT migrated here — see header comment.

# 2. settings-manifest.md (single file)
if [[ -f "$_LEGACY_MANIFEST" ]]; then
    _copy_one_file "$_LEGACY_MANIFEST" "$_DST_MANIFEST" || exit 1
    _any_work=1
fi

# ---------------------------------------------------------------------------
# Compat pointer: replace legacy ~/.claude/machine-local real dir with a
# platform-appropriate pointer to <settings-home>/machine-local.
#
# POSIX (Linux/macOS): symlink via ln -s — first-class, unchanged from prior.
# Windows (MINGW*/MSYS*/CYGWIN*): directory junction via cmd //c mklink /J.
#   A junction requires no elevation or Developer Mode, is transparent to consumer
#   file reads, and is the correct Windows primitive for a local-directory pointer.
#
# Both branches are first-class peers — not a fallback. Consumer reads of relocated
# TOML resolve live through the pointer on both platforms identically.
#
# Guards (both branches):
#   - Legacy path must be a real directory, not already a pointer (symlink/junction).
#     _is_pointer() detects POSIX symlinks ([[ -L ]]) and Windows directory junctions
#     (Python 3.8+ os.path.islink() returns True for junctions on Windows).
#   - Destination must exist (migration above guarantees this when legacy was present).
#
# Idempotency: once the pointer is in place, re-running is a clean no-op —
#   _is_pointer fires on the outer guard and the section is skipped.
#
# Fail-loud: link/junction creation failures exit non-zero with a platform-specific
#   remediation message. cygpath absence on a Windows run is also fail-loud.
# ---------------------------------------------------------------------------

# _is_pointer <path>: returns 0 if path is a POSIX symlink or Windows junction.
# Uses [[ -L ]] for the POSIX fast path; falls back to Python 3.8+ (coordinator hard
# dep) for Windows directory-junction detection (os.path.islink returns True for
# junctions on Python 3.8+). On POSIX the Python branch is unreachable in practice
# (symlinks are caught above), but it parses and runs harmlessly.
#
# Python interpreter fallback mirrors the canonical pattern in ensure-coordinator-venv.sh:295-298.
# If NO interpreter resolves, treat conservatively — prefer "is a pointer, skip" over
# "is a real dir, rm" to avoid data loss on a second run against a Windows junction.
_is_pointer() {
    local _p="$1"
    # POSIX symlink — fast path.
    [[ -L "$_p" ]] && return 0
    # Windows directory junction: Python 3.8+ os.path.islink() returns True for junctions.
    local _py=""
    if command -v python3 >/dev/null 2>&1; then _py=python3
    elif command -v python >/dev/null 2>&1; then _py=python
    fi
    if [[ -n "$_py" ]]; then
        "$_py" -c "import os,sys; exit(0 if os.path.islink(sys.argv[1]) else 1)" "$_p" 2>/dev/null \
            && return 0
        return 1
    fi
    # No Python interpreter found: cannot detect Windows directory junctions.
    # Treat conservatively — prefer "is a pointer, skip" over "is a real dir, rm"
    # to avoid data loss if this is called on a junction during a second run.
    echo "[migrate] WARNING: no python3 or python found; cannot detect Windows junctions." >&2
    echo "[migrate]   Treating '${_p}' as a pointer (conservative). Ensure python3 is on PATH and re-run." >&2
    return 0
}

if [[ -d "$_LEGACY_ML" ]] && ! _is_pointer "$_LEGACY_ML" && [[ -d "$_DST_ML" ]]; then
    _platform="$(uname -s 2>/dev/null || true)"
    case "$_platform" in
        MINGW*|MSYS*|CYGWIN*)
            # Windows path: directory junction via mklink /J.
            # cygpath (MSYS2/Git-for-Windows) converts POSIX paths to Windows paths;
            # required because mklink /J expects Windows-style paths and MSYS path
            # munging would otherwise corrupt them.
            if [[ "$_DRY_RUN" -eq 1 ]]; then
                echo "[migrate] DRY-RUN: would replace ${_LEGACY_ML} (real dir) with junction → ${_DST_ML}"
            else
                if ! command -v cygpath >/dev/null 2>&1; then
                    echo "migrate-substrate-to-settings-home: FATAL — cygpath not found on Windows host." >&2
                    echo "  cygpath is required to convert POSIX paths to Windows paths for mklink /J." >&2
                    echo "  Remediation: ensure cygpath is on PATH (provided by MSYS2, Cygwin, or Git-for-Windows)." >&2
                    exit 1
                fi
                _win_legacy="$(cygpath -w "$_LEGACY_ML")"
                _win_dst="$(cygpath -w "$_DST_ML")"
                # Junction-safe removal: rmdir removes a junction link without recursing
                # into its target (data-safe). Falls back to rm -rf only when $_LEGACY_ML
                # is a real non-empty directory (files already migrated to $_DST_ML above).
                # This guards against rm -rf recursing through a junction into $_DST_ML on
                # a second run if _is_pointer() missed the junction (e.g., no Python found).
                rmdir "$_LEGACY_ML" 2>/dev/null || rm -rf "$_LEGACY_ML"
                # popup-intentional-last-resort: cmd.exe is the only mechanism for
                # directory junctions on Windows; no Python subprocess alternative exists
                # for mklink /J. Runs only in MSYS/MINGW/CYGWIN shell environments
                # where a console is already attached — no popup occurs in practice.
                if ! cmd //c mklink /J "$_win_legacy" "$_win_dst" >/dev/null; then
                    echo "migrate-substrate-to-settings-home: FATAL — mklink /J failed." >&2
                    echo "  Link path: ${_win_legacy}" >&2
                    echo "  Target   : ${_win_dst}" >&2
                    echo "  Remediation: ensure cmd.exe is reachable and the target is a local NTFS path." >&2
                    echo "  Note: mklink /J does not require elevation or Developer Mode." >&2
                    exit 1
                fi
                echo "[migrate] installed compat junction: ${_LEGACY_ML} → ${_DST_ML}"
            fi
            ;;
        *)
            # POSIX (Linux/macOS): symlink — first-class, unchanged.
            if [[ "$_DRY_RUN" -eq 1 ]]; then
                echo "[migrate] DRY-RUN: would replace ${_LEGACY_ML} (real dir) with symlink → ${_DST_ML}"
            else
                rm -rf "$_LEGACY_ML"
                ln -s "$_DST_ML" "$_LEGACY_ML"
                echo "[migrate] installed compat symlink: ${_LEGACY_ML} → ${_DST_ML}"
            fi
            ;;
    esac
fi

if [[ "$_any_work" -eq 0 ]]; then
    echo "[migrate] nothing to migrate (no legacy source dirs/files present, or already migrated)"
fi

exit 0
