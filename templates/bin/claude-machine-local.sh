#!/usr/bin/env bash
# claude-machine-local.sh — sourced helper exporting $REPO_* for portable paths.
#
# Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md §5.2
# Purpose: make $REPO_PROJECT_RAG (and friends) cheaper to type than the
# hardcoded literal. Sourced once per shell session; idempotent.
#
# Settings-home contract (DR-072): the machine-local registry and its reader
# live under a settings home, not a fixed ~/.claude/bin path. Consumers MUST
# NOT invoke the bare-name `machine-local` wrapper to bootstrap — per
# docs/wiki/machine-local-registry.md:278, this script resolves the settings
# home by pure path arithmetic and invokes the reader impl directly:
#   <settings-home>/bin/_machine_local.py dump --prefix repos --format sh
# Settings-home resolution ladder (most-specific first; mirrors, but does not
# source, coordinator/lib/settings-home.sh — this file is installed standalone
# on a consumer machine where that lib is not guaranteed present):
#   1. $COORDINATOR_SETTINGS_HOME (if non-empty) → use verbatim
#   2. else ${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings
#
# Resolution: each $REPO_<SLUG> is resolved via the reader's `dump --format sh`,
# which resolves every repos.<slug> key through the same 4-rung ladder `get`
# uses (explicit flag/env → OS-keyed search-roots + marker autodiscovery →
# exceptions table → registry.local.toml fallback) in ONE process, and prints
# ready-to-`eval` guarded `export` statements. The reader owns both the per-key
# resolution and the key->$REPO_<SLUG> normalization, so this script costs
# exactly one process no matter how many repos are registered.
#
# Version-coupled to the reader: `--format sh` is required, and a settings-home
# whose `_machine_local.py` predates it exports NOTHING. That is loud by design
# (see the rc check at the eval below) — silent absence of every $REPO_* is far
# worse to debug than one error naming the fix.
#
# §4b idempotency (machine-local-registry.md §4b): each emitted export is
# gated (by the reader) on `[ -n "${VAR:-}" ] || export VAR=...` — re-sourcing
# in a child process does NOT clobber a deliberately pre-set $REPO_* override.
# The whole-script early-exit guard (CLAUDE_MACHINE_LOCAL_SOURCED) is retained
# for the common case (no pre-sets).
#
# Negative-spec: empty-string exports are suppressed. rc=1 (clean absence from
# the ladder) skips the export rather than exporting "" — exporting "" would
# corrupt "$REPO_FOO/subdir" path joins to "/subdir".
#
# Strict mode: set -e is intentionally absent — this file is sourced, so
# set -e would propagate to the caller's shell and kill it on any error.
#
# Usage:
#   source <settings-home>/bin/claude-machine-local.sh
#   echo "$REPO_PROJECT_RAG/subdir/file.py"

if [ -n "${CLAUDE_MACHINE_LOCAL_SOURCED:-}" ]; then
    return 0
fi

# Settings-home resolution ladder (inline mirror of
# coordinator/lib/settings-home.sh::_coordinator_settings_home — not sourced,
# see file-top note). Scope matches that lib: MACHINE_LOCAL_REGISTRY_DIR is a
# deeper registry-dir override handled by _machine_local.py itself, not here.
if [ -n "${COORDINATOR_SETTINGS_HOME:-}" ]; then
    _ml_settings_home="$COORDINATOR_SETTINGS_HOME"
else
    _ml_settings_home="${CLAUDE_HOME:-$HOME}/.coordinator-claude-settings"
fi
_ml_reader="$_ml_settings_home/bin/_machine_local.py"

# Interpreter probe: conservative, fail loud on absence rather than silently
# skipping the whole export ladder (silent-skip on a resolver is the named
# anti-pattern here — see coordinator/docs/wiki/machine-local-registry.md
# § 4 Resolution Order (formerly coordinator/CLAUDE.md § Build For Someone
# Else's Machine, retired 2026-07-27)).
if command -v python3 >/dev/null 2>&1; then
    _ml_python="python3"
elif command -v python >/dev/null 2>&1; then
    _ml_python="python"
else
    echo "claude-machine-local: error: no python3 or python interpreter found on PATH — cannot invoke $_ml_reader. Install Python 3 and re-source this file." >&2
    unset _ml_settings_home _ml_reader
    return 1
fi

# One process: `dump --format sh` resolves every repos.<slug> key through the
# full 4-rung ladder (incl. autodiscovery), normalizes each to $REPO_<SLUG>,
# and prints one guarded `export VAR='...'` line per resolved key — the guard
# (`[ -n "${VAR:-}" ] || export ...`) is the §4b idempotency gate, emitted by
# the reader itself so a pre-set $REPO_* override still wins. Declared-but-
# empty (AC14), cleanly-absent (rc=1), and operationally-failed (rc≥2) keys
# emit nothing on stdout — only a warning/error on stderr, which flows through
# uncaptured by this command substitution exactly as it did from the old
# per-key loop.
_ml_exports=$("$_ml_python" "$_ml_reader" dump --prefix repos --format sh)
_ml_rc=$?
if [ $_ml_rc -ne 0 ] && [ -z "$_ml_exports" ]; then
    # Nothing resolved AND the reader failed — most often a settings-home whose
    # _machine_local.py predates `--format sh` (argparse exits 2 on the unknown
    # flag). Every $REPO_* would silently be unset; say so instead.
    echo "claude-machine-local: error: reader at $_ml_reader failed (rc=$_ml_rc) and exported nothing — no \$REPO_* is set. If it predates 'dump --format sh', re-run the coordinator install to refresh it." >&2
else
    eval "$_ml_exports"
fi
unset _ml_settings_home _ml_reader _ml_python _ml_exports _ml_rc

export CLAUDE_MACHINE_LOCAL_SOURCED=1
