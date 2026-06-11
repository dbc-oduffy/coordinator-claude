#!/usr/bin/env bash
# verify-dist-publish-repo-sync.sh — Byte-identity check between Claude Central
# dist/ source-of-truth and the coordinator-claude publish repo for the two new
# flat-mirror targets.
#
# Usage:
#   verify-dist-publish-repo-sync.sh          Check all pairs; exit non-zero on any MISMATCH or MISSING.
#
# Targets verified (source → publish repo):
#   coordinator/dist/publish-repo-setup/      ↔  /x/coordinator-claude/setup/
#   coordinator/dist/publish-repo-toplevel/   ↔  /x/coordinator-claude/ (toplevel)
#
# ONE-WAY check only. Source IS the truth; publish repo is derivative.
# There is no --fix mode in v1 — the fix for an out-of-sync publish repo is
# always: bash setup/publish.sh <target>
#
# Why no --fix mode? Authority cite: plugin-extraction-and-distribution.md
# § Persona-Name Guard on Percolation — "publish.sh is the authority for
# percolation — manual cp is wrong." A script-driven copy would bypass
# depersonalize hooks and content-leakage scans that run as post-rsync hooks
# in the publish.sh pipeline.
#
# .percolate-ignore semantics (toplevel target only):
#   Files listed in dist/publish-repo-toplevel/.percolate-ignore are NOT verified
#   — they are publish-repo-owned infrastructure (CLAUDE.md, .gitignore, etc.)
#   that Claude Central deliberately does not author.
#
# Output format:
#   OK        <rel-path>   — byte-identical between source and publish repo
#   MISMATCH  <rel-path>   — content differs
#   MISSING   <rel-path>   — file absent in publish repo (a NEW source file not yet published)
#   IGNORED   <rel-path>   — excluded by .percolate-ignore (toplevel target)
#
# Exit codes:
#   0 — all verified files are byte-identical
#   1 — one or more MISMATCH or MISSING files detected
#   2 — source dir(s) not found (environment problem)
#
# Spec backlink: docs/plans/2026-05-21-back-percolate-publish-repo-orphans.md § Chunk 4

set -euo pipefail

# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# Publish repo root resolution (per global CLAUDE.md § Build For Someone Else's Machine):
#   env var → machine-local registry → fail-loud (no hardcoded fallback).
if [ -n "${COORDINATOR_CLAUDE_PUBLISH_REPO:-}" ]; then
    PUBLISH_REPO_ROOT="$COORDINATOR_CLAUDE_PUBLISH_REPO"
elif command -v machine-local >/dev/null 2>&1; then
    PUBLISH_REPO_ROOT="$(machine-local get repos.coordinator_claude 2>/dev/null || true)"
    if [ -z "$PUBLISH_REPO_ROOT" ]; then
        echo "ERROR  cannot resolve publish repo root: machine-local key 'repos.coordinator_claude' is unset" >&2
        echo "       Fix one of:" >&2
        echo "         (a) export COORDINATOR_CLAUDE_PUBLISH_REPO=/path/to/coordinator-claude" >&2
        echo "         (b) machine-local set repos.coordinator_claude /path/to/coordinator-claude" >&2
        exit 1
    fi
elif [ -x "$HOME/.claude/bin/machine-local" ]; then
    PUBLISH_REPO_ROOT="$("$HOME/.claude/bin/machine-local" get repos.coordinator_claude 2>/dev/null || true)"
    if [ -z "$PUBLISH_REPO_ROOT" ]; then
        echo "ERROR  cannot resolve publish repo root: machine-local key 'repos.coordinator_claude' is unset" >&2
        echo "       Fix one of:" >&2
        echo "         (a) export COORDINATOR_CLAUDE_PUBLISH_REPO=/path/to/coordinator-claude" >&2
        echo "         (b) ~/.claude/bin/machine-local set repos.coordinator_claude /path/to/coordinator-claude" >&2
        exit 1
    fi
else
    echo "ERROR  cannot resolve publish repo root: COORDINATOR_CLAUDE_PUBLISH_REPO is unset and machine-local is not available" >&2
    echo "       Fix one of:" >&2
    echo "         (a) export COORDINATOR_CLAUDE_PUBLISH_REPO=/path/to/coordinator-claude" >&2
    echo "         (b) install machine-local and run: machine-local set repos.coordinator_claude /path/to/coordinator-claude" >&2
    exit 1
fi

DIST_SETUP="$PLUGIN_ROOT/dist/publish-repo-setup"
DIST_TOPLEVEL="$PLUGIN_ROOT/dist/publish-repo-toplevel"
PUB_SETUP="$PUBLISH_REPO_ROOT/setup"
PUB_TOPLEVEL="$PUBLISH_REPO_ROOT"

# ---------------------------------------------------------------------------
# Pre-flight: verify source dirs exist
# ---------------------------------------------------------------------------
MISSING_DIRS=0
if [ ! -d "$DIST_SETUP" ]; then
    echo "ERROR  source dir not found: $DIST_SETUP" >&2
    MISSING_DIRS=1
fi
if [ ! -d "$DIST_TOPLEVEL" ]; then
    echo "ERROR  source dir not found: $DIST_TOPLEVEL" >&2
    MISSING_DIRS=1
fi
if [ ! -d "$PUB_SETUP" ]; then
    echo "ERROR  publish repo setup dir not found: $PUB_SETUP" >&2
    echo "       Is COORDINATOR_CLAUDE_PUBLISH_REPO set correctly?" >&2
    MISSING_DIRS=1
fi
if [ ! -d "$PUB_TOPLEVEL" ]; then
    echo "ERROR  publish repo root not found: $PUB_TOPLEVEL" >&2
    echo "       Is COORDINATOR_CLAUDE_PUBLISH_REPO set correctly?" >&2
    MISSING_DIRS=1
fi
if [ "$MISSING_DIRS" -ne 0 ]; then
    exit 2
fi

# ---------------------------------------------------------------------------
# Load .percolate-ignore for the toplevel target (if present)
# Portable replacement for declare -A: write entries to a temp file and
# use grep -qF for presence checks (works on bash 3.2 + BSD coreutils).
# ---------------------------------------------------------------------------
TOPLEVEL_PERCOLATE_IGNORE="$DIST_TOPLEVEL/.percolate-ignore"
_IGNORE_TMP="$(mktemp)"
trap 'rm -f "$_IGNORE_TMP"' EXIT

if [ -f "$TOPLEVEL_PERCOLATE_IGNORE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip blank lines and comments
        case "$line" in
            ''|'#'*) continue ;;
        esac
        printf '%s\n' "$line" >> "$_IGNORE_TMP"
    done < "$TOPLEVEL_PERCOLATE_IGNORE"
fi

_is_ignored() {
    grep -qxF "$1" "$_IGNORE_TMP" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
COUNT_VERIFIED=0
COUNT_MISMATCH=0
COUNT_MISSING=0

# ---------------------------------------------------------------------------
# Helper: compare one source file against its publish-repo counterpart
# ---------------------------------------------------------------------------
# Args: $1=source_file_path  $2=dest_file_path  $3=rel_path  $4=label_prefix
check_pair() {
    local src="$1"
    local dst="$2"
    local rel="$3"

    if [ ! -f "$dst" ]; then
        printf "%-10s %s\n" "MISSING" "$rel"
        COUNT_MISSING=$((COUNT_MISSING + 1))
        return
    fi

    if diff -q "$src" "$dst" >/dev/null 2>&1; then
        printf "%-10s %s\n" "OK" "$rel"
    else
        printf "%-10s %s\n" "MISMATCH" "$rel"
        COUNT_MISMATCH=$((COUNT_MISMATCH + 1))
    fi
    COUNT_VERIFIED=$((COUNT_VERIFIED + 1))
}

# ---------------------------------------------------------------------------
# Target 1: publish-repo-setup  (dist/publish-repo-setup/ ↔ /x/coordinator-claude/setup/)
# No .percolate-ignore for this target — all source files are verified.
# ---------------------------------------------------------------------------
echo "--- target: coordinator-claude-publish-repo-setup ---"

while IFS= read -r -d '' src_file; do
    rel="${src_file#"$DIST_SETUP/"}"
    dst_file="$PUB_SETUP/$rel"
    check_pair "$src_file" "$dst_file" "setup/$rel"
done < <(find "$DIST_SETUP" -maxdepth 1 -type f -print0 | sort -z)

# ---------------------------------------------------------------------------
# Target 2: publish-repo-toplevel  (dist/publish-repo-toplevel/ ↔ /x/coordinator-claude/)
# Respects .percolate-ignore — files listed there are skipped in both directions.
# Only files that ARE in source and NOT ignored are verified.
# ---------------------------------------------------------------------------
echo ""
echo "--- target: coordinator-claude-publish-repo-toplevel ---"

while IFS= read -r -d '' src_file; do
    rel="${src_file#"$DIST_TOPLEVEL/"}"

    # Skip directories (find -type f should already handle this, but be explicit)
    [ -f "$src_file" ] || continue

    # Check against .percolate-ignore list
    if _is_ignored "$rel"; then
        printf "%-10s %s\n" "IGNORED" "toplevel/$rel"
        continue
    fi

    dst_file="$PUB_TOPLEVEL/$rel"
    check_pair "$src_file" "$dst_file" "toplevel/$rel"
done < <(find "$DIST_TOPLEVEL" -maxdepth 1 -type f -print0 | sort -z)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "verified: $COUNT_VERIFIED, mismatched: $COUNT_MISMATCH, missing: $COUNT_MISSING"

# Exit non-zero on any drift
if [ "$COUNT_MISMATCH" -gt 0 ] || [ "$COUNT_MISSING" -gt 0 ]; then
    echo ""
    echo "DRIFT DETECTED — run: bash setup/publish.sh <target>"
    echo "  Do NOT copy files manually. publish.sh runs depersonalize hooks"
    echo "  and content-leakage scans that a manual cp bypasses."
    echo ""
    echo "  Note on MISMATCH false-positives:"
    echo "    publish-time-transform.sh rewrites dev-tree plugin paths to"
    echo "    publish-tree form at publish time (e.g. plugins/coordinator/"
    echo "    → plugins/coordinator/). Files whose source contains such paths will"
    echo "    report MISMATCH by design — the publish-tree version is the intended"
    echo "    OSS-facing shape. To distinguish real drift from path-rewrite delta:"
    echo "    diff the file by hand against the source, then mentally apply the"
    echo "    path-rewrite table. Real drift is content changes beyond the rewrite."
    exit 1
fi

exit 0
