#!/usr/bin/env bash
# lib/detect-existing-claude-home.test.sh — unit tests for detect-existing-claude-home.sh
#
# Spec backlink: chunk C7 — Track A/B detection helper (P8); three-state extension.
#
# The classifier emits: `state=<pristine|used-vanilla|configured> track=<A|B> reason: …`
# Each test asserts the expected state tier AND the backward-compat track letter.
#
# Coverage:
#   T1   Empty fixture                         → pristine     / A
#   T2   Real plugin subdir                    → configured   / B
#   T2b  Non-scaffolding file under plugins/   → configured   / B
#   T2c  Empty plugins/ subdir                 → used-vanilla / A (scaffolding, not real plugin)
#   T2d  Fresh CC scaffolding only             → used-vanilla / A (the old false-positive)
#   T2e  installed_plugins.json non-empty      → configured   / B
#   T2f  isolated empty-map (pretty-printed)   → used-vanilla / A (probes empty-map predicate)
#   T2g  non-empty map (pretty-printed)        → configured   / B (probes whitespace-strip)
#   T3   CLAUDE.md (substantial)               → used-vanilla / A (per taxonomy: not configured)
#   T3b  CLAUDE.md (stub)                      → used-vanilla / A
#   T4   git-init'd                            → configured   / B
#   T4b  Subdir of ancestor git repo           → pristine     / A (TARGET not git-tracked itself)
#   T5   Session artifacts (projects/)         → used-vanilla / A
#   T6   Coordinator infra (state/)            → configured   / B
#   T6b  coordinator.local.md                  → configured   / B
#   T7   Precedence: configured beats used     → configured   / B
#
# Self-contained: creates temp fixture dirs, runs the script against them,
# asserts stdout, then cleans up.  Exit 0 if all pass, 1 if any fail.

set -euo pipefail
# Distinguish a harness abort (missing git/mktemp, broken fixture) from a counted
# test failure — both otherwise exit 1. Without this, a mid-run abort silently
# drops the pass/fail tally and looks like an ordinary failure.
trap 'echo "HARNESS ABORT (unexpected error at line $LINENO) — not a counted test failure" >&2; exit 2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECTOR="$SCRIPT_DIR/detect-existing-claude-home.sh"

PASS=0
FAIL=0

_pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
_fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL+1)); }

# _assert <label> <dir> <expected-state> <expected-track>
_assert() {
    local label="$1" dir="$2" exp_state="$3" exp_track="$4" out
    out="$(bash "$DETECTOR" "$dir")"
    if [[ "$out" == "state=${exp_state} track=${exp_track} "* ]]; then
        _pass "$label"
    else
        _fail "$label" "expected state=${exp_state} track=${exp_track}, got: '$out'"
    fi
}

echo "=== detect-existing-claude-home.test.sh ==="

if [[ ! -f "$DETECTOR" ]]; then
    echo "FATAL: detector not found at $DETECTOR" >&2
    exit 1
fi

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# --- T1: empty fixture → pristine ------------------------------------------
echo "--- T1: empty fixture → pristine / A"
T1_DIR="$TMPROOT/pristine"; mkdir -p "$T1_DIR"
_assert "T1 empty → pristine" "$T1_DIR" pristine A

# --- T2: real plugin subdir → configured -----------------------------------
echo "--- T2: real plugin subdir → configured / B"
T2_DIR="$TMPROOT/with-plugin"; mkdir -p "$T2_DIR/plugins/my-plugin"
echo "plugin content" > "$T2_DIR/plugins/my-plugin/PLUGIN.md"
_assert "T2 plugin subdir → configured" "$T2_DIR" configured B

# --- T2b: non-scaffolding file directly under plugins/ → configured --------
echo "--- T2b: non-scaffolding file under plugins/ → configured / B"
T2B_DIR="$TMPROOT/with-plugin-file"; mkdir -p "$T2B_DIR/plugins"
echo "x" > "$T2B_DIR/plugins/some-plugin-file.md"
_assert "T2b plugin file → configured" "$T2B_DIR" configured B

# --- T2c: empty plugins/ subdir → used-vanilla (scaffolding, not real) -----
echo "--- T2c: empty plugins/ subdir → used-vanilla / A"
T2C_DIR="$TMPROOT/with-empty-plugin-dir"; mkdir -p "$T2C_DIR/plugins/empty-plugin"
_assert "T2c empty plugins/ subdir → used-vanilla" "$T2C_DIR" used-vanilla A

# --- T2d: FRESH Claude Code install (scaffolding only) → used-vanilla -------
# The exact historical false-positive: a zero-history machine must NOT be
# classified as an existing/configured setup.
echo "--- T2d: fresh Claude Code scaffolding → used-vanilla / A"
T2D_DIR="$TMPROOT/fresh-cc-install"
mkdir -p "$T2D_DIR/plugins/cache/some-marketplace" "$T2D_DIR/plugins/marketplaces"
printf '%s\n' '{"version": 2, "plugins": {}}' > "$T2D_DIR/plugins/installed_plugins.json"
printf '%s\n' '{}' > "$T2D_DIR/plugins/known_marketplaces.json"
printf '%s\n' '{}' > "$T2D_DIR/plugins/blocklist.json"
printf '%s\n' '{}' > "$T2D_DIR/plugins/plugin-catalog-cache.json"
printf '%s\n' 'sweep' > "$T2D_DIR/plugins/.last_inuse_sweep"
echo "x" > "$T2D_DIR/plugins/cache/some-marketplace/file"
_assert "T2d fresh CC scaffolding → used-vanilla" "$T2D_DIR" used-vanilla A

# --- T2e: installed_plugins.json non-empty → configured (B2a) --------------
echo "--- T2e: installed_plugins.json non-empty → configured / B"
T2E_DIR="$TMPROOT/cc-with-installed-plugin"; mkdir -p "$T2E_DIR/plugins"
printf '%s\n' '{"version": 2, "plugins": {"skill-creator@official": [{"scope":"user"}]}}' \
    > "$T2E_DIR/plugins/installed_plugins.json"
_assert "T2e installed_plugins.json non-empty → configured" "$T2E_DIR" configured B

# --- T2f: ISOLATED empty-map installed_plugins.json (pretty-printed) → used-vanilla
# Directly probes the empty-map path of _installed_plugins_json_nonempty with no
# confounding CC dirs: plugins/ holds ONLY this one file. A broken empty-map
# predicate would mis-fire configured here; the pretty-printing exercises the
# whitespace-strip. used-vanilla via U3 (_plugins_dir_nonempty).
echo "--- T2f: isolated pretty-printed empty installed_plugins.json → used-vanilla / A"
T2F_DIR="$TMPROOT/cc-empty-installed-pretty"; mkdir -p "$T2F_DIR/plugins"
printf '{\n  "version": 2,\n  "plugins": {}\n}\n' > "$T2F_DIR/plugins/installed_plugins.json"
_assert "T2f isolated empty-map (pretty) → used-vanilla" "$T2F_DIR" used-vanilla A

# --- T2g: pretty-printed NON-empty installed_plugins.json → configured (B2a) ---
# Exercises the whitespace-strip on a multi-line non-empty map (T2e was compact).
echo "--- T2g: pretty-printed non-empty installed_plugins.json → configured / B"
T2G_DIR="$TMPROOT/cc-installed-pretty"; mkdir -p "$T2G_DIR/plugins"
printf '{\n  "version": 2,\n  "plugins": {\n    "skill-creator@official": [\n      { "scope": "user" }\n    ]\n  }\n}\n' \
    > "$T2G_DIR/plugins/installed_plugins.json"
_assert "T2g pretty non-empty → configured" "$T2G_DIR" configured B

# --- T3: substantial CLAUDE.md → used-vanilla (per taxonomy, NOT configured) -
echo "--- T3: substantial CLAUDE.md → used-vanilla / A"
T3_DIR="$TMPROOT/with-claude-md"; mkdir -p "$T3_DIR"
{
    printf '# My Claude Config\n\n'
    for i in $(seq 1 11); do printf 'Non-blank line %d\n' "$i"; done
} > "$T3_DIR/CLAUDE.md"
_assert "T3 substantial CLAUDE.md → used-vanilla" "$T3_DIR" used-vanilla A

# --- T3b: stub CLAUDE.md → used-vanilla ------------------------------------
echo "--- T3b: stub CLAUDE.md → used-vanilla / A"
T3B_DIR="$TMPROOT/with-stub-claude-md"; mkdir -p "$T3B_DIR"
{ printf '# Stub\n\n'; for i in $(seq 1 5); do printf 'Line %d\n' "$i"; done; } > "$T3B_DIR/CLAUDE.md"
_assert "T3b stub CLAUDE.md → used-vanilla" "$T3B_DIR" used-vanilla A

# --- T4: git-init'd → configured -------------------------------------------
echo "--- T4: git-init'd → configured / B"
T4_DIR="$TMPROOT/git-tracked"; mkdir -p "$T4_DIR"
git -C "$T4_DIR" init --quiet
_assert "T4 git-tracked → configured" "$T4_DIR" configured B

# --- T4b: subdir of ancestor git repo → pristine (TARGET not tracked itself) -
echo "--- T4b: subdir of ancestor git repo → pristine / A"
T4B_PARENT="$TMPROOT/git-parent"; mkdir -p "$T4B_PARENT"
git -C "$T4B_PARENT" init --quiet
T4B_DIR="$T4B_PARENT/dot-claude"; mkdir -p "$T4B_DIR"
_assert "T4b subdir of ancestor repo → pristine" "$T4B_DIR" pristine A

# --- T5: session artifacts (projects/) → used-vanilla ----------------------
echo "--- T5: session artifacts → used-vanilla / A"
T5_DIR="$TMPROOT/used-projects"; mkdir -p "$T5_DIR/projects/some-project"
echo "x" > "$T5_DIR/history.jsonl"
_assert "T5 session artifacts → used-vanilla" "$T5_DIR" used-vanilla A

# --- T6: coordinator infra (state/) → configured ---------------------------
echo "--- T6: coordinator infra state/ → configured / B"
T6_DIR="$TMPROOT/coord-state"; mkdir -p "$T6_DIR/state"
_assert "T6 state/ → configured" "$T6_DIR" configured B

# --- T6b: coordinator.local.md → configured --------------------------------
echo "--- T6b: coordinator.local.md → configured / B"
T6B_DIR="$TMPROOT/coord-local-md"; mkdir -p "$T6B_DIR"
echo "project_type: x" > "$T6B_DIR/coordinator.local.md"
_assert "T6b coordinator.local.md → configured" "$T6B_DIR" configured B

# --- T7: precedence — configured signal beats used-vanilla signals ---------
# A home with BOTH session history AND git-tracking must classify as configured.
echo "--- T7: precedence (git + sessions) → configured / B"
T7_DIR="$TMPROOT/configured-and-used"; mkdir -p "$T7_DIR/projects"
echo "# config" > "$T7_DIR/CLAUDE.md"
git -C "$T7_DIR" init --quiet
_assert "T7 configured beats used → configured" "$T7_DIR" configured B

# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -gt 0 ]] && exit 1
exit 0
