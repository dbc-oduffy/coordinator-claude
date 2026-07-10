#!/usr/bin/env bash
# lib/coordinator-safe-name.sh — cross-platform safe filename component primitives
#
# Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § seam 1
#
# PURPOSE: Define the canonical NTFS-illegal charset and three pure functions
# (csn_timestamp, csn_slug, csn_check) that shell consumers source directly.
# The block-illegal-filename hook and coordinator-safe-name CLI both source this lib.
#
# PORTABILITY CONTRACT (DR-148):
#   - bash ≥4 + BSD/GNU coreutils required at runtime
#   - macOS /bin/bash 3.2: this lib PARSES on 3.2 (no bash-4-only syntax at
#     the top level) — runtime requires bash ≥4 (install brew bash per DR-148)
#   - Uses tr '[:upper:]' '[:lower:]' NOT the bash-4 lowercase operator (bash-4-only)
#   - Uses grep -E NOT grep -P (GNU-only PCRE; absent on BSD)
#   - Does NOT self-locate via shell source-array lookups — constants + pure
#     functions only. The CLI wrapper ($0-relative path resolution) sources us.
#
# NEGATIVE-SPEC: Do NOT add path-resolution logic or shell source-array references
# to this file. The no-self-location contract is tested by coordinator-safe-name.test.sh.

# ---------------------------------------------------------------------------
# Canonical NTFS-illegal charset (the SoT for shell consumers)
# ---------------------------------------------------------------------------
# These characters make a filename component illegal or unresolvable on Windows
# (NTFS / VFAT) and cause `git checkout` failures on non-Windows hosts when the
# tree is checked out on Windows. `U+F03A` (private-use full-width colon) exists
# precisely because the real colon `:` (U+003A) is the Windows ADS separator.
# Trailing dot and trailing space are also NTFS-illegal on Windows even though
# they are not characters per se — NTFS silently strips them, breaking the path.
#
# Illegal chars: : ? * < > | " \ /
# Also illegal: ASCII control chars (0x00-0x1F, 0x7F DEL)
# Also illegal: trailing dot or trailing space (not chars, but structural rules)
CSN_ILLEGAL_CHARS=':?*<>|"\/'

# ---------------------------------------------------------------------------
# csn_timestamp [--now | --mtime <file>]
# ---------------------------------------------------------------------------
# Emit a UTC timestamp in the colon-free form YYYY-MM-DDTHH-MM-SSZ.
# Default (no args or --now): current time via `date -u`.
# --mtime <file>: derive from the file's mtime via the canonical 3-way chain:
#   BSD stat FIRST (ordering is load-bearing — GNU date -r reads its arg as epoch
#   seconds on BSD, silently mis-deriving the wrong timestamp if placed first).
csn_timestamp() {
    local mode="--now"
    local file=""

    case "${1:-}" in
        --now | "")
            mode="--now"
            ;;
        --mtime)
            mode="--mtime"
            file="${2:-}"
            if [ -z "$file" ]; then
                printf 'csn_timestamp: --mtime requires a file argument\n' >&2
                return 1
            fi
            ;;
        *)
            printf 'csn_timestamp: unknown option "%s"\n' "$1" >&2
            printf 'Usage: csn_timestamp [--now | --mtime <file>]\n' >&2
            return 1
            ;;
    esac

    if [ "$mode" = "--now" ]; then
        date -u "+%Y-%m-%dT%H-%M-%SZ"
        return $?
    fi

    # --mtime path: canonical 3-way epoch derivation
    # BSD stat -f %m FIRST; GNU stat -c %Y second; date -r FILE last.
    # Rationale: GNU date -r reads its arg as epoch-seconds on BSD, so placing
    # any date-r probe before BSD stat would silently mis-derive on macOS.
    #
    # Each probe output is validated as a purely-numeric string before use.
    # GNU stat -f on Linux/Git-Bash outputs filesystem info (not file mtime)
    # but exits 0 — the numeric-validation guard prevents that wrong output
    # from poisoning the chain and allowing the || to fall through correctly.
    local epoch="" _epoch_try

    _epoch_try=$(stat -f %m "$file" 2>/dev/null)
    case "$_epoch_try" in
        [0-9]*) epoch="$_epoch_try" ;;
    esac

    if [ -z "$epoch" ]; then
        _epoch_try=$(stat -c %Y "$file" 2>/dev/null)
        case "$_epoch_try" in
            [0-9]*) epoch="$_epoch_try" ;;
        esac
    fi

    if [ -z "$epoch" ]; then
        _epoch_try=$(date -r "$file" +%s 2>/dev/null)
        case "$_epoch_try" in
            [0-9]*) epoch="$_epoch_try" ;;
        esac
    fi

    if [ -z "$epoch" ]; then
        printf 'csn_timestamp: cannot read mtime of "%s"\n' "$file" >&2
        return 1
    fi

    # Format epoch → UTC colon-free.
    # BSD date: date -u -r EPOCH (reads arg as epoch seconds)
    # GNU date:  date -u -d @EPOCH (@ prefix signals epoch input)
    date -u -r "$epoch" "+%Y-%m-%dT%H-%M-%SZ" 2>/dev/null \
        || date -u -d "@$epoch" "+%Y-%m-%dT%H-%M-%SZ"
}

# ---------------------------------------------------------------------------
# csn_slug "<text>"
# ---------------------------------------------------------------------------
# Emit a [a-z0-9-]-only slug, ≤40 chars, no leading/trailing hyphen.
# Mirrors coordinator-doc-new._slug_from_title (Python, bin/coordinator-doc-new:295)
# and coordinator-lesson-promote._slug_from_title (Python, bin/coordinator-lesson-promote:311).
# Those Python impls are independent / pre-existing / not refactored by this plan.
# This function is the SHELL-SIDE SoT for slug generation.
csn_slug() {
    local text="${1:-}"
    local slug

    # Lowercase → replace any non-alphanum run with a single hyphen → trim
    slug=$(printf '%s' "$text" \
        | tr '[:upper:]' '[:lower:]' \
        | tr -c 'a-z0-9' '-' \
        | tr -s '-')

    # Strip leading and trailing hyphens
    slug="${slug#-}"
    slug="${slug%-}"

    # Cap at 40 chars
    slug="${slug:0:40}"

    # A truncation at 40 might leave a trailing hyphen; strip it
    slug="${slug%-}"

    printf '%s\n' "$slug"
}

# ---------------------------------------------------------------------------
# csn_check "<component>"
# ---------------------------------------------------------------------------
# Exit 0 if the filename component is safe for all target platforms (NTFS,
# macOS HFS+, Linux ext4, Git-Bash checkout).
# Exit non-zero + stderr message naming the offending char if the component
# contains any NTFS-illegal character, a control character, or has a trailing
# dot or trailing space.
# This is the canonical predicate reused by the block-illegal-filename hook.
csn_check() {
    local comp="${1:-}"

    # Trailing dot (NTFS silently strips it, breaking paths)
    case "$comp" in
        *.) printf 'csn_check: trailing dot in "%s"\n' "$comp" >&2; return 1 ;;
    esac

    # Trailing space (same NTFS stripping hazard)
    case "$comp" in
        *" ") printf 'csn_check: trailing space in "%s"\n' "$comp" >&2; return 1 ;;
    esac

    # NTFS-illegal characters — one case per char so the pattern quoting is
    # explicit and portable across bash 3.2+ (avoid ambiguous glob chars in
    # unquoted positions inside case patterns).
    case "$comp" in
        *":"*)  printf 'csn_check: illegal char ":" in "%s"\n'  "$comp" >&2; return 1 ;;
    esac
    case "$comp" in
        *"?"*)  printf 'csn_check: illegal char "?" in "%s"\n'  "$comp" >&2; return 1 ;;
    esac
    case "$comp" in
        *"*"*)  printf 'csn_check: illegal char "*" in "%s"\n'  "$comp" >&2; return 1 ;;
    esac
    case "$comp" in
        *"<"*)  printf 'csn_check: illegal char "<" in "%s"\n'  "$comp" >&2; return 1 ;;
    esac
    case "$comp" in
        *">"*)  printf 'csn_check: illegal char ">" in "%s"\n'  "$comp" >&2; return 1 ;;
    esac
    # Pipe: quoted inside double-quotes is a literal in a bash case pattern
    # (no alternation ambiguity — the | alternation operator is only special
    # UNQUOTED between case pattern alternatives). Pure-bash, zero subprocesses.
    case "$comp" in
        *"|"*) printf 'csn_check: illegal char "|" in "%s"\n' "$comp" >&2; return 1 ;;
    esac
    case "$comp" in
        *'"'*)  printf 'csn_check: illegal char "\"" in "%s"\n' "$comp" >&2; return 1 ;;
    esac
    case "$comp" in
        *"\\"*) printf 'csn_check: illegal char "\\" in "%s"\n' "$comp" >&2; return 1 ;;
    esac
    case "$comp" in
        *"/"*)  printf 'csn_check: illegal char "/" in "%s"\n'  "$comp" >&2; return 1 ;;
    esac

    # ASCII control chars (0x00-0x1F and 0x7F DEL)
    # bash case supports POSIX bracket expressions in glob patterns — no subprocess needed.
    case "$comp" in
        *[[:cntrl:]]*) printf 'csn_check: control character in "%s"\n' "$comp" >&2; return 1 ;;
    esac

    return 0
}
