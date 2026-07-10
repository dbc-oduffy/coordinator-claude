#!/usr/bin/env bash
# verify-cc-root-source-guard-sync.sh — Verify that every in-scope CLAUDE_PLUGIN_ROOT
# resolve-site in the coordinator corpus carries the guard shape appropriate to its
# CLASS, AND that no guard (function-call or inline) is placed where it would be a
# functionally-dead no-op.
#
# THREE-CLASS MODEL (v3split-01 §C5 promotion — coordinator_trusted_root_guard is
# now a sourced function, but not every site is expected to call it):
#
#   1. FUNCTION-CALL sites (default/fallthrough class) — shell scripts under
#      hooks/scripts/, bin/, lib/ that migrated: expected to source
#      coordinator-trusted-root-guard.sh via a BASH_SOURCE/dirname-relative trusted
#      path and CALL coordinator_trusted_root_guard --mode=.... Checked by
#      check_file_guards(..., "call") — scans 12 lines after each resolve-site for
#      the GUARD_CALL_MARKER. Unguarded here is a genuine incomplete-migration
#      finding, not a checker bug.
#
#   2. KNOWN-DEFERRED sites (is_known_deferred(), KNOWN_DEFERRED_INLINE allowlist
#      below) — a short, explicit list of files whose migration is blocked by
#      concurrent uncommitted work (see docs/plans/2026-07-09-resolver-unification-
#      v3split-01.md remainder table). Checked by check_file_guards(..., "inline") —
#      byte-matches the inline trust-core against the SSOT core (INLINE_CORE_MARKERS)
#      and reports a "KNOWN-DEFERRED" note, not a failure, on a clean match. A
#      drifted inline copy still fails.
#
#   3. DOC-INLINE sites (is_doc_inline_class(): any .md file, or any .sh file under
#      a /tests/ path segment) — self-contained instruction blocks (SKILL.md,
#      commands/*.md, docs/wiki/*.md) or test fixtures that legitimately keep the
#      inline guard forever (sourcing a lib is fragile in a copy-paste-into-ad-hoc-
#      Bash context, or the fixture is testing guard behavior as data). Checked the
#      same way as class 2 (byte-match, "inline" mode) but with no KNOWN-DEFERRED
#      note — this is by-design permanent, not a migration backlog item.
#
# This replaced a two-state model (pre-C5: byte-identical grep-scan for everyone;
# immediately-post-C5: call-site-presence for everyone) — both single-mode passes
# mis-classified ~40 class-2/3 sites as UNGUARDED because they correctly never
# migrated to a function call.
#
# Presence alone is not sufficient (LESSON-DRIVEN: state/lessons/2026-07-06-presence-check-
# verifiers-are-blind-to-gu.yaml — a prior sweep broke 6 lifecycle helpers by stamping an
# unconditional `/../`-traversal guard onto a var whose legitimate primary value contains
# `/../`; a presence-only verifier reported them OK). This script therefore ALSO runs a
# PLACEMENT lint (check_file_placement, below) that flags a guard call placed unconditionally
# on a var whose primary assignment is `/../`-bearing and NOT runtime-normalized via
# `$(cd ... && pwd)` — i.e. it is blind neither to absence NOR to a present-but-dead guard.
# This lint is ORTHOGONAL to the three-class model above and applies uniformly to all
# classes over the same in-scope consumer set.
#
# Usage:
#   verify-cc-root-source-guard-sync.sh             Verify all in-scope sites (3-class + placement). Exit non-zero on any finding.
#   verify-cc-root-source-guard-sync.sh --list      List all in-scope consumer files (after exclusion filter).
#   verify-cc-root-source-guard-sync.sh --dry-run   Print unified diff of proposed insertions (alias: --diff).
#   verify-cc-root-source-guard-sync.sh --fix        Idempotent auto-insert guard at every unguarded site.
#   verify-cc-root-source-guard-sync.sh --fix --dry-run  Dry-run wins: diff only, no writes.
#
# NOTE (v3split-01 §C5-check): --fix/--dry-run still insert the OLD inline guard-core +
# tail text extracted from the SSOT's numbered bash code blocks — that inserter was NOT
# in this chunk's scope (the plan names only the verify-mode presence+placement swap) and
# is now stale relative to the promoted coordinator_trusted_root_guard function; its
# block-index extraction (bash blocks 1/2/3) also drifted when an earlier chunk (C5-core)
# added a new leading example block to the SSOT, shifting the numbered core/tail blocks to
# 2/3/4. Left untouched here as an out-of-scope pre-existing condition — flagged to the EM.
#
# Exclusion list (documented — these sites are NOT required to carry the guard):
#   Self-reference non-consumers (3 files): mention the pattern in text/code-blocks but are
#     NOT live resolve-sites.
#
#   NOTE — empty-fallback sites (="$\{CLAUDE_PLUGIN_ROOT:-}") are NOT excluded.
#   The :-} empty default only covers the UNSET case; when an attacker sets
#   CLAUDE_PLUGIN_ROOT=/tmp/evil, these sites resolve to /tmp/evil and then source/exec
#   from it. They are in-scope consumers and require the fail-open guard variant.
#
# Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C5
# Prior spec: docs/plans/2026-07-06-cc-root-source-guard-corpus-wide.md § C1
# Tripwire: docs/wiki/coordinator-tripwires.md § CLAUDE-PLUGIN-ROOT-SOURCE-GUARD
# SSOT (guard shape doc-of-record): coordinator/snippets/cc-root-source-guard.md
# SSOT (sourced implementation): coordinator/lib/coordinator-trusted-root-guard.sh

set -euo pipefail

# Resolve plugin root using BASH_SOURCE-relative resolution (avoids a CLAUDE_PLUGIN_ROOT
# bootstrap dependency in the guard-verification script itself).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
fi

SNIPPET_FILE="$PLUGIN_ROOT/snippets/cc-root-source-guard.md"
if [ ! -f "$SNIPPET_FILE" ]; then
    echo "ERROR: canonical snippet not found at $SNIPPET_FILE" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# CLI argument parsing — supports --fix, --dry-run/--diff, --list, and combinations.
# --fix --dry-run: dry-run wins (diff output only, no writes).
# ---------------------------------------------------------------------------
MODE="verify"
_DRY_RUN=0
for _arg in "$@"; do
    case "$_arg" in
        --fix)           MODE="fix" ;;
        --dry-run|--diff) _DRY_RUN=1 ;;
        --list)          MODE="list" ;;
    esac
done
[ "$_DRY_RUN" = 1 ] && MODE="dryrun"

# ---------------------------------------------------------------------------
# KNOWN-DEFERRED inline allowlist (v3split-01 §C5 three-way classification).
#
# These two shell sites still carry the OLD inline `_cc_trusted=0` trust-core
# (byte-identical to the SSOT's Trusted-prefix core, coordinator/snippets/
# cc-root-source-guard.md) instead of sourcing + calling the promoted
# `coordinator_trusted_root_guard` function. Their migration is BLOCKED by
# concurrent uncommitted work at the time of this checker redesign, not by
# checker limitation — see the remainder table in
# docs/plans/2026-07-09-resolver-unification-v3split-01.md for the tracked
# migrate-when-clear item. Verify mode byte-matches their inline guard
# against the SSOT core (the OLD behavior) and reports a one-line
# "KNOWN-DEFERRED" note instead of UNGUARDED. A drifted inline copy at either
# site (bytes no longer matching the SSOT) still fails the check — this
# allowlist waives the "must call the function" requirement, not the
# "inline copy must not drift" requirement.
# ---------------------------------------------------------------------------
KNOWN_DEFERRED_INLINE=(
    # no deferred sites remain — resolver-unification v3split-01 completed the shell corpus
)

is_known_deferred() {
    local fpath="$1"
    local suffix
    for suffix in "${KNOWN_DEFERRED_INLINE[@]}"; do
        case "$fpath" in
            *"/$suffix"|"$suffix") return 0 ;;
        esac
    done
    return 1
}

# ---------------------------------------------------------------------------
# Exclusion list — paths relative to PLUGIN_ROOT parent (the repo root).
# Normalised to have no leading slash and no trailing slash for suffix-matching.
# ---------------------------------------------------------------------------
EXCLUDED_SUFFIXES=(
    # self-reference non-consumers: these files contain the pattern for documentation/tooling reasons, not as live resolve sites
    "coordinator/snippets/cc-root-source-guard.md"              # SSOT — contains the pattern in markdown code blocks
    "coordinator/bin/verify-cc-root-source-guard-sync.sh"       # this script — pattern appears in comments and as a string literal
    "coordinator/docs/wiki/coordinator-tripwires.md"            # tripwire registry — mentions the pattern in documentation prose
    # auto-fix test fixtures: these files contain the idiom as test DATA; --fix would corrupt them; verify/--list counts would be polluted
    "coordinator/bin/tests/fixtures/cc-root-source-guard-fix"   # entire fixtures dir — input/expected files intentionally contain unguarded sites
    # placement-lint self-test: heredoc content contains a deliberately broken fixture; scanning
    # it as a corpus consumer would produce a spurious PLACEMENT-VIOLATION
    "coordinator/bin/tests/test-cc-root-guard-placement-lint.sh"
    # NOTE: empty-fallback sites (="${CLAUDE_PLUGIN_ROOT:-}") are intentionally NOT listed here.
    # They ARE in-scope consumers — when CLAUDE_PLUGIN_ROOT is set to an attacker-controlled path,
    # these sites resolve to that path and source/exec from it. The :-} empty default only covers
    # the unset case. These sites require the fail-open guard variant (Variant B).
)

is_excluded() {
    local fpath="$1"
    # Finding 4 (defense-in-depth): exclude per-file tmpfiles created by --fix.
    # If SIGINT leaves an orphan .cc-guard-fix.PID file next to a consumer, it
    # must not be re-processed as a live resolve-site on subsequent runs.
    case "$fpath" in *.cc-guard-fix.*) return 0 ;; esac
    local suffix
    for suffix in "${EXCLUDED_SUFFIXES[@]}"; do
        # Match when the file path ends with the exclusion suffix (exact file),
        # or is a file nested anywhere under the exclusion suffix (directory prefix).
        case "$fpath" in
            *"/$suffix"|"$suffix"|*"/$suffix/"*) return 0 ;;
        esac
    done
    return 1
}

# ---------------------------------------------------------------------------
# Finding 1 (2026-07-09 checker redesign): root-DEFINITION sites are not
# consumer/guard targets.
#
# A resolve-site of the form `<var>="${CLAUDE_PLUGIN_ROOT:-...}"` is a
# CONSUMER (reads a possibly-attacker-controlled root to source/exec from —
# in scope for the guard) UNLESS its LHS identifier is `CLAUDE_PLUGIN_ROOT`
# itself, in which case the line DEFINES/exports the var's own value (e.g.
# `export CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$COORD_ROOT}"` in
# install-maximalist.sh:81, establishing the plugin root during cold
# install-time bootstrap before any trust decision is even meaningful).
# Guarding a definition-site would break cold-install bootstrap — there is
# nothing to validate yet; the var IS the thing being established. Detected
# by matching the resolve-site line against the fixed string
# `CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-` (optionally preceded by
# `export `/whitespace) — i.e. LHS identifier == CLAUDE_PLUGIN_ROOT.
# ---------------------------------------------------------------------------
DEFINITION_SITE_FIXED='CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-'

is_definition_site_line() {
    local line="$1"
    case "$line" in
        *"$DEFINITION_SITE_FIXED"*) return 0 ;;
    esac
    return 1
}

# ---------------------------------------------------------------------------
# Variant selection for --fix: fail-open (Variant B) vs fail-loud (Variant A).
# Fail-open sites: advisory hooks under hooks/scripts/ + 6 empty-fallback files
# where sourcing an empty string is the expected degraded-mode behavior.
# Fail-loud sites: all other in-scope consumers.
# ---------------------------------------------------------------------------
FAIL_OPEN_SUFFIXES=(
    "coordinator/bin/prune-closed-bugs.sh"
    "coordinator/bin/sweep-shipped-handoffs.sh"
    "coordinator/bin/sweep-terminal-plans.sh"
    "coordinator/hooks/scripts/session-ensure-branch.sh"
    "coordinator/lib/resolve-coordinator-clone.sh"
    "coordinator/skills/workstream-complete/tests/test-wsc-invoke-wire-contract.sh"
)

is_fail_open() {
    local fpath="$1"
    # hooks/scripts/* is always fail-open (advisory hook chain must not hard-exit)
    case "$fpath" in
        */hooks/scripts/*) return 0 ;;
    esac
    # 6 explicit empty-fallback sites
    local suffix
    for suffix in "${FAIL_OPEN_SUFFIXES[@]}"; do
        case "$fpath" in
            *"/$suffix"|"$suffix") return 0 ;;
        esac
    done
    return 1
}

# ---------------------------------------------------------------------------
# DOC-INLINE classification (v3split-01 §C5 three-way classification, class 3).
#
# Two shapes legitimately keep the inline `_cc_trusted=0` trust-core forever
# rather than migrating to a sourced-function call:
#
#   (a) Markdown-embedded copies — coordinator/skills/**/SKILL.md,
#       coordinator/commands/*.md, and any other .md doc (e.g. docs/wiki/*.md)
#       carrying the guard in a fenced bash example. These are self-contained
#       instruction blocks an agent copies verbatim into ad-hoc Bash — sourcing
#       a lib file is fragile in that context (no stable BASH_SOURCE chain),
#       so the doc intentionally keeps the guard byte-inline. Detected
#       generically by file extension (.md), not a path allowlist — a
#       doc-inline copy is a property of being markdown, not of living under
#       one specific directory.
#
#   (b) Shell test fixtures — any .sh file whose path contains a `/tests/`
#       directory segment (coordinator/bin/tests/test-*.sh,
#       coordinator/skills/*/tests/test-*.sh). These exercise the guard
#       behavior itself as test DATA/fixture content; sourcing the real lib
#       would couple the fixture to production source-path resolution the
#       test is specifically trying to hold fixed. Detected by the `/tests/`
#       path segment, not an explicit file list — the class is structural
#       (any current or future test fixture under a tests/ dir), not a fixed
#       enumeration.
#
# Neither shape is expected to call coordinator_trusted_root_guard; verify
# mode instead byte-matches their inline copy against the SSOT core (the
# pre-C5 behavior) and reports OK (not UNGUARDED) on a clean match.
# ---------------------------------------------------------------------------
is_doc_inline_class() {
    local fpath="$1"
    case "$fpath" in
        *.md) return 0 ;;
        */tests/*.sh) return 0 ;;
    esac
    return 1
}

# ---------------------------------------------------------------------------
# Find in-scope consumer files
# grep -rlE: list files containing the LHS-agnostic resolve-site pattern.
# The pattern matches any variable assignment of the form: <var>="${CLAUDE_PLUGIN_ROOT:-
# (The backslash-dollar is a bash literal; we pass the unescaped form to grep.)
# ---------------------------------------------------------------------------
find_consumers() {
    local raw_files
    raw_files="$(grep -rlE '="\$\{CLAUDE_PLUGIN_ROOT:-' "$PLUGIN_ROOT" 2>/dev/null || true)"
    [ -z "$raw_files" ] && return 0

    local f
    while IFS= read -r f; do
        is_excluded "$f" && continue
        # Finding 1: a file whose ONLY resolve-site line(s) are root-DEFINITION
        # sites (LHS == CLAUDE_PLUGIN_ROOT) is not a consumer — skip it entirely.
        # A file mixing a definition line with a genuine consumer line still
        # surfaces (grep -c below counts total resolve-site lines; if any
        # non-definition line exists among them, the file remains in scope).
        local _resolve_lines _def_lines
        # grep -c always prints a numeric count (0 on no-match) AND exits 1 on
        # no-match; under `set -e` that exit code kills the script unless
        # neutralized, but an `|| echo 0` fallback after -c double-fires
        # (grep's own "0" plus the fallback's "0" both hit stdout), producing
        # a two-line value that breaks `[ -eq ]`. `|| true` after the whole
        # assignment neutralizes set -e without touching what was captured —
        # grep -c's own printed count (already correct on both match and
        # no-match) is preserved untouched.
        _resolve_lines="$(grep -cE '="\$\{CLAUDE_PLUGIN_ROOT:-' "$f" 2>/dev/null)" || true
        _def_lines="$(grep -cF "$DEFINITION_SITE_FIXED" "$f" 2>/dev/null)" || true
        if [ "$_resolve_lines" -gt 0 ] && [ "$_resolve_lines" -eq "$_def_lines" ]; then
            continue
        fi
        printf '%s\n' "$f"
    done <<< "$raw_files" | sort
}

CONSUMERS="$(find_consumers)"

if [ -z "$CONSUMERS" ]; then
    echo "no in-scope consumers found — nothing to verify"
    exit 0
fi

# ---------------------------------------------------------------------------
# Shared constants used by both --fix and verify modes
# ---------------------------------------------------------------------------

# Guard-core marker — the third line of the trusted-prefix core (unique, first-occurrence reliable).
# Used ONLY by --fix mode's own idempotency check (has this inserter already stamped its
# own inline copy at this site?) — --fix's inserter shape was not in this chunk's scope,
# see the file-header NOTE (v3split-01 §C5-check) above.
GUARD_MARKER="_cc_trusted=0"

# Call-site marker for the promoted function — used by verify mode (check_file_guards)
# to confirm a resolve-site is guarded by a CALL to coordinator_trusted_root_guard,
# not by presence of the (now-obsolete-at-migrated-sites) inline trust-core marker above.
GUARD_CALL_MARKER="coordinator_trusted_root_guard"

# Resolve-site pattern passed as a fixed string to awk/index (avoids awk regex metachar issues).
RESOLVE_SITE_FIXED='="${CLAUDE_PLUGIN_ROOT:-'

# ---------------------------------------------------------------------------
# --list mode
# ---------------------------------------------------------------------------
if [ "$MODE" = "list" ]; then
    echo "$CONSUMERS"
    exit 0
fi

# ---------------------------------------------------------------------------
# --fix / --dry-run mode: idempotent auto-inserter (blueprint §2).
#
# Algorithm: single awk program per consumer file (load-all-lines + END-pass
# with insert_after accumulation). Guard text is sourced from the SSOT snippet
# (coordinator/snippets/cc-root-source-guard.md) — never hand-typed here.
# Variant selection: fail-open for hooks/scripts/* + 6 empty-fallback files;
# fail-loud for all other in-scope sites.
# Idempotency: skip occurrence when _cc_trusted=0 appears in lines[i+1..i+12].
# Safety: temp-file + mv (write only on awk exit 0); cleaned on EXIT.
#
# Spec backlink: docs/plans/2026-07-06-cc-root-source-guard-corpus-wide.delivery-blueprint.md §2
# ---------------------------------------------------------------------------
if [ "$MODE" = "fix" ] || [ "$MODE" = "dryrun" ]; then

    # Temp dir for SSOT block extractions — cleaned on EXIT
    _CC_GUARD_TMP="$(mktemp -d)"
    # Finding 4: track per-file tmpfiles for EXIT-trap cleanup (guards against
    # SIGINT between awk-success and mv/rm leaving an orphan .cc-guard-fix.PID file).
    _CC_GUARD_TMPFILES=()
    _cleanup_guard_tmp() {
        rm -rf "$_CC_GUARD_TMP" 2>/dev/null || true
        [ "${#_CC_GUARD_TMPFILES[@]}" -gt 0 ] && rm -f "${_CC_GUARD_TMPFILES[@]}" 2>/dev/null || true
    }
    trap _cleanup_guard_tmp EXIT

    _CORE_FILE="$_CC_GUARD_TMP/core.txt"
    _TAIL_LOUD="$_CC_GUARD_TMP/tail-loud.txt"
    _TAIL_OPEN="$_CC_GUARD_TMP/tail-open.txt"

    # Extract the three bash code blocks from the SSOT (1=core, 2=Variant A, 3=Variant B)
    awk '/^```bash[[:space:]]*$/{c++;if(c==1){f=1;next}} f&&/^```[[:space:]]*$/{f=0;next} f{print}' \
        "$SNIPPET_FILE" > "$_CORE_FILE"
    awk '/^```bash[[:space:]]*$/{c++;if(c==2){f=1;next}} f&&/^```[[:space:]]*$/{f=0;next} f{print}' \
        "$SNIPPET_FILE" > "$_TAIL_LOUD"
    awk '/^```bash[[:space:]]*$/{c++;if(c==3){f=1;next}} f&&/^```[[:space:]]*$/{f=0;next} f{print}' \
        "$SNIPPET_FILE" > "$_TAIL_OPEN"

    if [ ! -s "$_CORE_FILE" ] || [ ! -s "$_TAIL_LOUD" ] || [ ! -s "$_TAIL_OPEN" ]; then
        echo "ERROR: SSOT block extraction failed — expected 3 bash code blocks in $SNIPPET_FILE" >&2
        exit 1
    fi

    _FIX_WROTE=0
    _FIX_SKIPPED=0

    while IFS= read -r _F; do
        # Determine file type (fence-tracking needed for .md)
        case "$_F" in *.md) _FT="md" ;; *) _FT="sh" ;; esac

        # Variant selection (blueprint §2.6)
        if is_fail_open "$_F"; then
            _TAIL_FILE="$_TAIL_OPEN"
        else
            _TAIL_FILE="$_TAIL_LOUD"
        fi

        # Per-file temp output (same dir as source for atomic mv)
        _TMPF="${_F}.cc-guard-fix.$$"
        _CC_GUARD_TMPFILES+=("$_TMPF")   # Finding 4: track for EXIT-trap cleanup

        # Transform: load-all-lines END-pass with insert_after accumulation (blueprint §2.2)
        if awk \
            -v resolve_fixed="$RESOLVE_SITE_FIXED" \
            -v guard_marker="$GUARD_MARKER" \
            -v file_type="$_FT" \
            -v core_file="$_CORE_FILE" \
            -v tail_file="$_TAIL_FILE" \
            '
BEGIN {
    core_count = 0
    while ((getline ln < core_file) > 0) { core_lines[++core_count] = ln }
    close(core_file)
    tail_count = 0
    while ((getline ln < tail_file) > 0) { tail_lines[++tail_count] = ln }
    close(tail_file)
    in_fence = 0; insertions = 0
}
# Finding 2: str_gsub — safe literal-string replace via index/substr splice.
# Avoids awk gsub metacharacter expansion: & expands to the matched text and
# \ is an escape prefix, so an lhs containing && would double to _cc_root_cc_root.
function str_gsub(str, old, rep,    result, olen, pos) {
    result = ""; olen = length(old)
    while ((pos = index(str, old)) > 0) {
        result = result substr(str, 1, pos - 1) rep
        str = substr(str, pos + olen)
    }
    return result str
}
{ lines[NR] = $0 }
END {
    for (i = 1; i <= NR; i++) {
        if (file_type == "md") {
            if (lines[i] ~ /^[[:space:]]*```bash[[:space:]]*$/) { in_fence = 1 }
            else if (in_fence && lines[i] ~ /^[[:space:]]*```[[:space:]]*$/) { in_fence = 0 }
        }
        is_sh_ctx = (file_type == "sh" || in_fence)
        # Review: code-reviewer (A-F1) — skip comment lines; a commented-out resolve
        # pattern is not a live resolve-site and must not receive a guard insertion.
        if (is_sh_ctx && index(lines[i], resolve_fixed) > 0 && !(lines[i] ~ /^[[:space:]]*#/)) {
            already = 0
            lim = i + 12; if (lim > NR) lim = NR
            for (j = i + 1; j <= lim; j++) {
                if (lines[j] ~ /^[[:space:]]*#/) continue   # Review: A-F1 — skip comment lines in guard-marker scan
                if (index(lines[j], guard_marker) > 0) { already = 1; break }
            }
            if (!already) {
                pos = index(lines[i], resolve_fixed)
                pre = substr(lines[i], 1, pos - 1)
                # Finding 1: extract trailing identifier from the pre-= substring.
                # Handles bare (VAR=), keyword-prefixed (local/declare/export VAR=),
                # and compound-command (... && VAR=) forms uniformly — avoids
                # capturing the whole prefix as the "var".
                lhs = ""
                if (match(pre, /[A-Za-z_][A-Za-z0-9_]*$/)) {
                    lhs = substr(pre, RSTART, RLENGTH)
                }
                # Finding 3: validate extracted identifier; emit WARNING and skip
                # on non-match (leave unguarded for hand-routing — shows UNGUARDED
                # in verify, which is the honest signal; never insert a malformed guard).
                if (lhs !~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
                    print "WARNING: cc-root-guard: cannot extract identifier, skipping line " i " in " FILENAME ": " lines[i] > "/dev/stderr"
                } else if (lhs == "_cc_doe" || lhs == "_cc_trusted") {
                    # Review: code-reviewer (A-F6) — lhs collides with guard-internal variable names;
                    # str_gsub would rename _cc_root→lhs inside the guard body itself, corrupting
                    # the guard dataflow (the case/[ checks would reference the wrong variable).
                    print "WARNING: cc-root-guard: lhs=" lhs " collides with guard-internal var, skipping line " i " in " FILENAME > "/dev/stderr"
                } else {
                    indent = lines[i]; sub(/[^[:space:]].*/, "", indent)
                    guard = ""
                    for (k = 1; k <= core_count; k++) {
                        ck = str_gsub(core_lines[k], "_cc_root", lhs)
                        guard = guard indent ck "\n"
                    }
                    for (k = 1; k <= tail_count; k++) {
                        tk = str_gsub(tail_lines[k], "_cc_root", lhs)
                        guard = guard indent tk "\n"
                    }
                    insert_after[i] = guard
                    insertions++
                }
            }
        }
        print lines[i]
        if (i in insert_after) printf "%s", insert_after[i]
    }
}
            ' "$_F" > "$_TMPF"
        then
            if diff -q "$_F" "$_TMPF" > /dev/null 2>&1; then
                # Already guarded — no change
                rm -f "$_TMPF"
                _FIX_SKIPPED=$((_FIX_SKIPPED + 1))
            elif [ "$MODE" = "dryrun" ]; then
                diff -u "$_F" "$_TMPF" || true
                rm -f "$_TMPF"
                _FIX_WROTE=$((_FIX_WROTE + 1))
            else
                # Review: code-reviewer (A-F4) — non-atomic write tradeoff: cat > truncates
                # $_F at open then streams content; a SIGKILL or disk-full mid-write leaves
                # $_F zero-byte with the original content unrecoverable ($_TMPF is also gone
                # via the EXIT trap). Accepted tradeoff: the prior mv was atomic but stripped
                # exec bits on some platforms; cat > preserves them at the cost of atomicity.
                cat "$_TMPF" > "$_F" && rm -f "$_TMPF"
                echo "FIXED        $_F"
                _FIX_WROTE=$((_FIX_WROTE + 1))
            fi
        else
            echo "ERROR: awk transform failed on $_F" >&2
            rm -f "$_TMPF"
        fi
    done <<< "$CONSUMERS"

    if [ "$MODE" = "dryrun" ]; then
        echo ""
        echo "Dry-run: $_FIX_WROTE file(s) would be modified, $_FIX_SKIPPED already guarded."
    else
        echo ""
        echo "Fixed: $_FIX_WROTE file(s) modified, $_FIX_SKIPPED already guarded."
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# verify mode — three-class per-resolve-site check (v3split-01 §C5).
#
# Post-C5-promotion, the guard corpus splits into three legitimate shapes;
# a single "does a function call appear nearby" test (the pre-redesign
# behavior) mis-classified classes 2 and 3 as UNGUARDED — ~40 false
# positives on files that were never supposed to migrate. check_file_guards
# now takes an explicit `site_class` and applies the matching check:
#
#   call     — class 1 (function-call sites: hooks/scripts, bin, lib that
#              migrated). Scans the next 12 lines for a CALL to
#              coordinator_trusted_root_guard (GUARD_CALL_MARKER). This is
#              the original call-site-presence check, unchanged.
#   inline   — class 2 (KNOWN-DEFERRED) and class 3 (doc-inline / test
#              fixture) sites. Byte-matches the inline trust-core AGAINST
#              THE SSOT — every one of INLINE_CORE_MARKERS must appear
#              within the scan window, not just the single `_cc_trusted=0`
#              marker the old grep-scan used. A site missing even one
#              marker (partial/drifted copy) still fails here; this is
#              stricter than presence-of-one-marker, which is the point —
#              class 2/3 sites are supposed to carry a byte-identical copy,
#              and drift should fail loud, not silently pass on a substring
#              hit.
#
# 12-line window (both modes) accommodates the guard body / call plus
# intervening comments/blank lines — unchanged from the pre-redesign window.
#
# Presence alone is NOT proof the guard is effective — see check_file_placement
# below, which pairs this presence check with a placement lint for the
# functionally-dead-guard bug class documented in
# state/lessons/2026-07-06-presence-check-verifiers-are-blind-to-gu.yaml.
# ---------------------------------------------------------------------------

# Inline trust-core markers (LHS-agnostic — "_cc_root" below is a literal
# substring shared by every site regardless of the site's actual LHS var
# name, e.g. sites using $QR or $_ahs_helper still contain these literal
# fragments because they are hand-fixed constants in the SSOT core, not
# copies of the LHS var itself). Kept in sync with
# coordinator/snippets/cc-root-source-guard.md's Trusted-prefix core block
# (lines 30-38 as of this writing) — update both together if the core ever
# changes; the snippet is dynamic-discovery / not registry-enrolled, so
# there is no automated cross-check (see the snippet's own header note).
INLINE_CORE_MARKERS=(
    '_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root"'
    '_cc_doe="${_cc_doe%/}"'
    '_cc_trusted=0'
    'case "$'
    'COORDINATOR_PLUGIN_ROOT_TRUSTED:-'
)

check_file_guards() {
    local file="$1"
    local resolve_fixed="$2"
    local guard_fixed="$3"
    local site_class="$4"   # "call" (class 1) or "inline" (class 2/3)
    # Review: code-reviewer (A-F2) — detect file type so verify and --fix agree on which
    # lines are resolve-sites in .md files (non-bash fenced blocks must be skipped).
    local _ft
    case "$file" in *.md) _ft="md" ;; *) _ft="sh" ;; esac

    if [ "$site_class" = "inline" ]; then
        # Byte-match mode: ALL markers in INLINE_CORE_MARKERS must appear
        # within the 12-line scan window for the site to count as guarded.
        # Markers are joined with a \x01 separator (not newline) — macOS's
        # /usr/bin/awk (onetrueawk derivative) fails to parse a -v value
        # containing an embedded newline alongside embedded double-quotes
        # ("awk: newline in string ... at source line 1"); \x01 is not a
        # character any marker contains, so it round-trips safely.
        local markers_joined
        markers_joined="$(printf '%s\x01' "${INLINE_CORE_MARKERS[@]}")"
        awk -v rf="$resolve_fixed" -v file_type="$_ft" -v markers_str="$markers_joined" -v sep=$'\x01' '
            BEGIN {
                n_markers = split(markers_str, markers, sep)
            }
            { lines[NR] = $0 }
            END {
                in_fence = 0
                for (i = 1; i <= NR; i++) {
                    if (file_type == "md") {
                        if (lines[i] ~ /^[[:space:]]*```bash[[:space:]]*$/) { in_fence = 1 }
                        else if (in_fence && lines[i] ~ /^[[:space:]]*```[[:space:]]*$/) { in_fence = 0 }
                    }
                    is_sh_ctx = (file_type == "sh" || in_fence)
                    if (is_sh_ctx && index(lines[i], rf) > 0 && !(lines[i] ~ /^[[:space:]]*#/)) {
                        limit = i + 12
                        if (limit > NR) limit = NR
                        for (m = 1; m <= n_markers; m++) {
                            if (markers[m] == "") continue   # trailing empty split element
                            found_m = 0
                            for (j = i + 1; j <= limit; j++) {
                                if (index(lines[j], markers[m]) > 0) { found_m = 1; break }
                            }
                            if (!found_m) { print i; break }
                        }
                    }
                }
            }
        ' "$file"
    else
        # Call-site-presence mode (class 1) — unchanged single-marker scan.
        awk -v rf="$resolve_fixed" -v gf="$guard_fixed" -v file_type="$_ft" '
            { lines[NR] = $0 }
            END {
                in_fence = 0
                for (i = 1; i <= NR; i++) {
                    # Review: A-F2 — replicate --fix fence-tracking: only count resolve-sites
                    # inside bash fences for .md files (matches --fix mode behaviour).
                    if (file_type == "md") {
                        if (lines[i] ~ /^[[:space:]]*```bash[[:space:]]*$/) { in_fence = 1 }
                        else if (in_fence && lines[i] ~ /^[[:space:]]*```[[:space:]]*$/) { in_fence = 0 }
                    }
                    is_sh_ctx = (file_type == "sh" || in_fence)
                    # Review: A-F1 — skip comment lines to avoid false UNGUARDED on commented-out patterns.
                    if (is_sh_ctx && index(lines[i], rf) > 0 && !(lines[i] ~ /^[[:space:]]*#/)) {
                        found = 0
                        limit = i + 12
                        if (limit > NR) limit = NR
                        for (j = i + 1; j <= limit; j++) {
                            if (lines[j] ~ /^[[:space:]]*#/) continue   # Review: A-F1 — skip comment lines in marker scan
                            if (index(lines[j], gf) > 0) {
                                found = 1
                                break
                            }
                        }
                        if (!found) print i
                    }
                }
            }
        ' "$file"
    fi
}

# ---------------------------------------------------------------------------
# Placement-lint helper: detect a trust guard placed unconditionally on a
# variable whose /../ primary assignment makes it self-defeating.
#
# Target bug class (fixed in 24bdfe9): a guard
#   case "$VAR" in *"/.."*) _cc_trusted=0 ;; esac
# — or, post-v3split-01 §C5 promotion, the equivalent call-site form
#   coordinator_trusted_root_guard --mode=... --root="$VAR" --site="$0"
# placed unconditionally when VAR's PRIMARY assignment contains /../
# (e.g. _cli_path="${_self_dir}/../bin/foo.js") causes the guard to always
# fire and reject its own trusted path — the guard is PRESENT (presence check
# passes) but semantically broken. This lint pairs with the call-site-presence
# check above precisely because presence alone cannot distinguish a live guard
# from a functionally-dead one (state/lessons/2026-07-06-presence-check-
# verifiers-are-blind-to-gu.yaml).
#
# Safe form: the guard is confined inside an if [[ ! -f "$VAR" ]]; then ... fi
# block so it only runs when VAR holds the CLAUDE_PLUGIN_ROOT fallback value,
# not the BASH_SOURCE-relative primary (which legitimately contains /../).
#
# Two trigger shapes are recognized on each line (both funnel into the same
# backward-scan + gate-check below — legacy inline sites and post-C5-migration
# call sites are lint-equivalent):
#   (1) legacy inline traversal guard: case "$VAR" in *"/.."*)
#   (2) promoted-function call site:   coordinator_trusted_root_guard ... --root="$VAR"
#
# Detection heuristic — for each trigger line naming VAR:
#   (a) Scan backwards (window: 100 lines) for a V= assignment whose RHS
#       contains the literal text /../.
#   (b) If found, scan between that assignment and the guard for a line
#       containing BOTH "if" AND "! -f \"$V" — the if-gate that confines
#       the guard to the fallback branch.  If absent -> PLACEMENT-VIOLATION.
#
# Known heuristic limits (false-positives acceptable; false-negatives on the
# exact unconditional-guard bug class are the invariant):
#   • 100-line backwards window: an assignment further away is not detected.
#     No known corpus case exceeds this range.
#   • Gate detection requires "if" on the same source line as "! -f "$V"":
#     a multi-line if condition would escape detection. No known corpus case.
#   • A clean reassignment of V between the /../ primary and the guard (e.g.
#     V="/clean/path" then guard) may produce a false positive. Review confirms.
#   • $(cd ... && pwd) runtime-normalized primaries are EXCLUDED from the /../
#     trigger (the cd-walk always resolves to an absolute path with no literal
#     /../ segment at runtime) — only a literal /../ that survives to runtime
#     (BASH_SOURCE-relative sibling hops) is the target bug class.
#
# Prints PLACEMENT-VIOLATION lines to stderr; exits 1 if any found, else 0.
# Spec backlink: docs/plans/2026-07-06-cc-root-guard-placement-lint.md
#                docs/plans/2026-07-09-resolver-unification-v3split-01.md § C5
# ---------------------------------------------------------------------------
check_file_placement() {
    local file="$1"
    awk '
    BEGIN { violations = 0 }
    { lines[NR] = $0 }
    END {
        for (i = 1; i <= NR; i++) {
            line = lines[i]
            var = ""

            # --- Trigger shape (1): legacy inline traversal guard: case "$VAR" in *"/.."*) ---
            cs_pos = index(line, "case \"$")
            if (cs_pos > 0 && index(line, "\"/..\"*)") > 0) {
                var_start = cs_pos + 7
                rest = substr(line, var_start)
                q = index(rest, "\"")
                if (q >= 2) var = substr(rest, 1, q - 1)
            }

            # --- Trigger shape (2): promoted-function call site with --root="$VAR" ---
            if (var == "" && index(line, "coordinator_trusted_root_guard") > 0) {
                rp = index(line, "--root=\"$")
                if (rp > 0) {
                    var_start = rp + 9
                    rest = substr(line, var_start)
                    q = index(rest, "\"")
                    if (q >= 2) var = substr(rest, 1, q - 1)
                }
            }

            if (var == "" || var !~ /^[A-Za-z_][A-Za-z0-9_]*$/) continue

            # Scan backwards (up to 100 lines) for a /../ primary assignment of VAR
            found_assign = 0; assign_at = 0
            win_start = (i - 100 > 1) ? i - 100 : 1
            eq_str = var "="
            for (j = i - 1; j >= win_start; j--) {
                ln = lines[j]
                ep = index(ln, eq_str)
                if (ep == 0) continue
                # Guard: char immediately before VAR must not be alnum/_ (LHS check)
                if (ep > 1 && substr(ln, ep - 1, 1) ~ /[A-Za-z0-9_]/) continue
                # Check RHS (after the =) contains the literal text /../
                # Skip assignments where /../ is inside a $(cd ... && pwd) subshell:
                # those always produce a resolved absolute path (no /../ at runtime).
                # Pattern: RHS contains "&& pwd" indicates a cd-walk resolution.
                rhs = substr(ln, ep + length(eq_str))
                if (index(rhs, "/../") > 0 && index(rhs, "&& pwd") == 0) {
                    found_assign = 1; assign_at = j; break
                }
            }
            if (!found_assign) continue
            # Scan between primary and guard for an if-gate:
            # a line containing BOTH "if" AND "! -f \"$VAR"
            gated = 0
            nf_sig = "! -f \"$" var
            for (k = assign_at + 1; k < i; k++) {
                if (index(lines[k], "if") > 0 && index(lines[k], nf_sig) > 0) {
                    gated = 1; break
                }
            }
            if (!gated) {
                print "PLACEMENT-VIOLATION  " FILENAME ":" i "  var=" var \
                    " -- guard rejects its own /../ primary;" \
                    " confine to the [[ ! -f ]] fallback" > "/dev/stderr"
                violations++
            }
        }
        if (violations > 0) exit 1
    }
    ' "$file"
}

EXIT_CODE=0
PLACEMENT_EXIT_CODE=0

# ---------------------------------------------------------------------------
# Per-consumer three-way classification (v3split-01 §C5):
#   1. KNOWN-DEFERRED  — is_known_deferred(): inline byte-match, note not fail.
#   2. DOC-INLINE       — is_doc_inline_class(): inline byte-match, no note.
#   3. FUNCTION-CALL    — everything else: call-site-presence check.
# is_known_deferred is checked BEFORE is_doc_inline_class since the deferred
# allowlist is a (small, .sh-only) subset that would otherwise fall through
# to the function-call class — the two checks are mutually exclusive in
# practice (the deferred files are neither .md nor under /tests/) but the
# ordering documents the precedence explicitly rather than relying on that
# coincidence.
#
# is_known_deferred files get a TWO-STAGE check: try the call-site check
# first — the allowlist names files whose migration was blocked AT THE TIME
# this checker was written, but a listed file may have since been migrated
# by concurrent work landing after this checker's authoring (the allowlist
# is a point-in-time snapshot, not a live gate). A file that now calls the
# function is reported OK like any class-1 site; only a file that STILL
# carries the old inline core (byte-match) is reported KNOWN-DEFERRED. If
# neither check passes, it's a genuine UNGUARDED finding.
# ---------------------------------------------------------------------------
while IFS= read -r consumer; do
    if is_known_deferred "$consumer"; then
        CALL_UNGUARDED="$(check_file_guards "$consumer" "$RESOLVE_SITE_FIXED" "$GUARD_CALL_MARKER" "call")"
        if [ -z "$CALL_UNGUARDED" ]; then
            echo "OK           $consumer  (deferred allowlist entry already migrated — see KNOWN_DEFERRED_INLINE note)"
        else
            UNGUARDED_LINES="$(check_file_guards "$consumer" "$RESOLVE_SITE_FIXED" "$GUARD_CALL_MARKER" "inline")"
            if [ -z "$UNGUARDED_LINES" ]; then
                echo "KNOWN-DEFERRED (migrate when concurrent work clears): $consumer"
            else
                echo "UNGUARDED [inline-drift]  $consumer"
                while IFS= read -r lineno; do
                    echo "             line $lineno: $(sed -n "${lineno}p" "$consumer" | sed 's/^[[:space:]]*//')"
                done <<< "$UNGUARDED_LINES"
                EXIT_CODE=1
            fi
        fi
    elif is_doc_inline_class "$consumer"; then
        UNGUARDED_LINES="$(check_file_guards "$consumer" "$RESOLVE_SITE_FIXED" "$GUARD_CALL_MARKER" "inline")"
        if [ -z "$UNGUARDED_LINES" ]; then
            echo "OK           $consumer"
        else
            echo "UNGUARDED [doc-inline-drift]  $consumer"
            while IFS= read -r lineno; do
                echo "             line $lineno: $(sed -n "${lineno}p" "$consumer" | sed 's/^[[:space:]]*//')"
            done <<< "$UNGUARDED_LINES"
            EXIT_CODE=1
        fi
    else
        UNGUARDED_LINES="$(check_file_guards "$consumer" "$RESOLVE_SITE_FIXED" "$GUARD_CALL_MARKER" "call")"
        if [ -z "$UNGUARDED_LINES" ]; then
            echo "OK           $consumer"
        else
            # Review: code-reviewer (A-F5) — annotate with the expected variant so a developer
            # reading verify output knows which guard to apply without consulting the source.
            echo "UNGUARDED [$(is_fail_open "$consumer" && echo 'B/fail-open' || echo 'A/fail-loud')]  $consumer"
            while IFS= read -r lineno; do
                echo "             line $lineno: $(sed -n "${lineno}p" "$consumer" | sed 's/^[[:space:]]*//')"
            done <<< "$UNGUARDED_LINES"
            EXIT_CODE=1
        fi
    fi
    # Placement lint — runs over the same in-scope consumer set; violations go to stderr
    if ! check_file_placement "$consumer"; then
        PLACEMENT_EXIT_CODE=1
    fi
done <<< "$CONSUMERS"

if [ "$EXIT_CODE" -ne 0 ]; then
    echo ""
    echo "ACTION: run 'verify-cc-root-source-guard-sync.sh --dry-run' to preview, then '--fix' to insert."
    echo "  SSOT: $SNIPPET_FILE"
fi

[ "$PLACEMENT_EXIT_CODE" -ne 0 ] && EXIT_CODE=1
exit "$EXIT_CODE"
