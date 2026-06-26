#!/usr/bin/env bash
# bin/check-machine-path-leak.sh — Tripwire: prevent machine-specific absolute paths from
# being committed into tracked configuration files.
#
# Purpose: Guards against the "thislaptop leak" pattern — where a developer's local home
# directory or drive-letter path lands in tracked settings.json (directory-source marketplace
# entries, mcpServers paths, etc.) or working-repos.yaml (repo catalog paths). These paths
# are machine-specific and must live in gitignored per-machine files, not in the shared
# tracked tree.
#
# Severity contract:
#   settings.json  — HARD block. Any machine-absolute-path leaf value → exit 1.
#   working-repos.yaml — SOFT warn. Current-machine $HOME-rooted paths → stderr WARN,
#                        exit 0. Foreign machine paths (X:\, E:\, /Users/other/) are
#                        intentional catalog content and are NOT flagged.
#
# Negative-spec (hard-won):
#   - Does NOT grep raw file text — structural JSON/YAML parsing only. Text-grep
#     false-positives on fixtures, commit-message args, and comment blocks.
#   - Does NOT flag X:\, E:\, or /Users/<other>/ paths in working-repos.yaml — those
#     are the documented Machine-A catalog and must stay in the file.
#   - Only flags paths rooted at the CURRENT machine's $HOME in working-repos.yaml.
#   - settings.json is always a hard block regardless of path origin.
#
# Spec backlink: docs/plans/2026-06-23-machine-path-leak-guard.md
#
# Usage:
#   check-machine-path-leak.sh [--staged] [<file> ...]
#
#   --staged       Read staged file list from `git diff --cached --name-only` and
#                  inspect any settings.json or working-repos.yaml in that list.
#                  (default when no file arguments are given)
#   <file> ...     Explicit file path(s) to inspect. Useful for CI or ad-hoc checks.
#
# Exit codes:
#   0 — OK (no hard violations; soft warns printed to stderr but do not fail)
#   1 — VIOLATION: settings.json contains a machine-specific absolute path leaf value
#   2 — ERROR: unexpected failure (not a git repo, python3 missing, etc.)
#
# Output:
#   stdout — human-readable status lines
#   stderr — violation details and error messages
#
# Environment:
#   HOME  — used to determine the current machine's home directory for working-repos.yaml
#            soft-warn matching. Defaults to the shell's $HOME.
#
# Windows subprocess note: python3 invocations below are Unix `exec` calls from bash, not
# Windows CreateProcess calls. This script runs as a git commit-time guard on macOS/Linux.
# # popup-safe-env-suppressed

# Review: reviewer — nit Finding 13: siblings (check-schema-version-bump.sh) use `set -uo pipefail`
# (no -e). Keeping consistent — the || true guards below handle non-zero subshells explicitly.
set -uo pipefail

# ---------------------------------------------------------------------------
# Bash ≥ 4 guard (DR-148)
# ---------------------------------------------------------------------------

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    echo "check-machine-path-leak.sh: ERROR — requires bash ≥ 4 (found ${BASH_VERSION})" >&2
    echo "  Install via Homebrew: brew install bash" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Resolve python3
# ---------------------------------------------------------------------------

PY3="$(command -v python3 2>/dev/null)" || {
    echo "check-machine-path-leak.sh: ERROR — python3 is required but not found in PATH" >&2
    exit 2
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

MODE="staged"
EXPLICIT_FILES=()

for arg in "$@"; do
    case "$arg" in
        --staged)
            MODE="staged"
            ;;
        -h|--help)
            sed -n '2,/^# Negative-spec/p' "$0" | grep '^#' | sed 's/^# \?//' || true
            exit 0
            ;;
        -*)
            echo "check-machine-path-leak.sh: unknown argument: $arg" >&2
            exit 2
            ;;
        *)
            EXPLICIT_FILES+=("$arg")
            MODE="explicit"
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Collect candidate files to inspect
# ---------------------------------------------------------------------------

SETTINGS_FILES=()
WORKING_REPOS_FILES=()

_collect_file() {
    local f="$1"
    local base
    base="$(basename "$f")"
    case "$base" in
        settings.json)
            SETTINGS_FILES+=("$f")
            ;;
        working-repos.yaml)
            WORKING_REPOS_FILES+=("$f")
            ;;
    esac
}

if [[ "$MODE" == "staged" ]]; then
    # Must be inside a git repo
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        echo "check-machine-path-leak.sh: ERROR — not a git repository" >&2
        exit 2
    fi
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        _collect_file "$line"
    done < <(git diff --cached --name-only 2>/dev/null)
else
    for f in "${EXPLICIT_FILES[@]}"; do
        _collect_file "$f"
    done
fi

# ---------------------------------------------------------------------------
# Python snippet: walk all JSON leaf string values, match machine-absolute-path
# patterns INSIDE Python, and emit only violating leaves as NUL-separated
# "leaf.path\x00leaf_value\x00" pairs.
#
# Doing the match inside Python eliminates:
#   (a) per-leaf bash subprocess overhead (was one python3 call per JSON leaf)
#   (b) the TAB channel that corrupted IFS-split when JSON values contained tabs
#
# SETTINGS.JSON ONLY — must NEVER be used for working-repos.yaml, where
# X:\, E:\, and /Users/<other>/ are intentional Machine-A catalog content.
#
# Patterns (kept in sync with the working-repos check which has its own logic):
#   ^/Users/<name>/    macOS home
#   ^/home/<name>/     Linux home
#   ^C:[/\]Users[/\]   Windows C:\Users\
#   ^X:[/\]            Machine-A X:\ catalog drive
#   ^E:[/\]            Machine-A E:\ dev drive
# ---------------------------------------------------------------------------

SCAN_SETTINGS_JSON_PY='
import sys, json, re

PATTERNS = [
    r"^/Users/[^/]+/",
    r"^/home/[^/]+/",
    r"^C:[/\\]Users[/\\]",
    r"^X:[/\\]",
    r"^E:[/\\]",
]

def is_machine_abs(val):
    for p in PATTERNS:
        if re.search(p, val):
            return True
    return False

def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = (path + "." + k) if path else k
            walk(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, path + "[" + str(i) + "]")
    elif isinstance(obj, str):
        if is_machine_abs(obj):
            # NUL-separated: cannot appear in JSON strings; safe channel
            sys.stdout.buffer.write(path.encode() + b"\x00" + obj.encode() + b"\x00")

try:
    data = json.load(sys.stdin)
    walk(data)
except json.JSONDecodeError as e:
    sys.stderr.write("ERROR: invalid JSON: " + str(e) + "\n")
    sys.exit(2)
'

# ---------------------------------------------------------------------------
# Check: settings.json — HARD block
# ---------------------------------------------------------------------------

HARD_VIOLATION=0

_check_settings_json() {
    local file="$1"
    local content

    # Read from git index if the file does not exist on disk
    if [[ -f "$file" ]]; then
        content="$(cat "$file")"
    elif git rev-parse --git-dir >/dev/null 2>&1; then
        content="$(git show ":${file}" 2>/dev/null)" || {
            # File deleted from index — nothing to check
            return
        }
    else
        echo "check-machine-path-leak.sh: WARN — ${file} not found on disk" >&2
        return
    fi

    # Review: reviewer — P2 Finding 3: use mktemp for unpredictable tmp path (TOCTOU fix).
    # Two temp files: one for stderr capture, one for NUL-separated violation output.
    # NUL bytes cannot survive bash $() command substitution (bash strips them), so we
    # write violations to a temp file and read with `read -d $'\0'` from a process
    # substitution instead.
    local tmp_err tmp_violations
    tmp_err="$(mktemp 2>/dev/null || echo "/tmp/_cmpL_err_$$")"
    tmp_violations="$(mktemp 2>/dev/null || echo "/tmp/_cmpL_viol_$$")"

    local py_rc=0
    "$PY3" -c "$SCAN_SETTINGS_JSON_PY" <<< "$content" >"$tmp_violations" 2>"$tmp_err" || py_rc=$?

    if [[ $py_rc -ne 0 ]]; then
        local errmsg
        errmsg="$(cat "$tmp_err" 2>/dev/null)"
        rm -f "$tmp_err" "$tmp_violations"
        echo "check-machine-path-leak.sh: ERROR — failed to parse ${file} as JSON: ${errmsg}" >&2
        HARD_VIOLATION=1
        return
    fi
    rm -f "$tmp_err"

    # Parse NUL-separated pairs: leaf_path\x00leaf_value\x00 ...
    # No per-leaf subprocess — matching was done inside Python above.
    # Reading from file (not variable) preserves embedded NUL bytes.
    local leaf_path leaf_val
    while IFS= read -r -d $'\0' leaf_path <&3 && IFS= read -r -d $'\0' leaf_val <&3; do
        echo "VIOLATION: ${file}: machine-specific path in JSON leaf" >&2
        echo "  Leaf path : ${leaf_path}" >&2
        echo "  Value     : ${leaf_val}" >&2
        echo "  Remedy    : machine-specific paths must live in gitignored" >&2
        echo "              settings.local.json or machine-local registry," >&2
        echo "              not in tracked settings.json" >&2
        HARD_VIOLATION=1
    done 3< "$tmp_violations"
    rm -f "$tmp_violations"
}

for sf in "${SETTINGS_FILES[@]}"; do
    _check_settings_json "$sf"
done

# ---------------------------------------------------------------------------
# Python snippet: walk all YAML leaf string values and emit only leaves
# rooted at CURRENT_HOME as NUL-separated "leaf.path\x00leaf_value\x00" pairs.
#
# Doing the match inside Python eliminates the TAB channel (TABs inside YAML
# string values would corrupt IFS=$'\t' read -r splits). NUL cannot appear in
# a YAML string value, making it a safe separator.
#
# NOTE: working-repos.yaml soft-warn only flags paths rooted at the CURRENT
# machine's $HOME. X:\, E:\, and /Users/<other>/ are intentional Machine-A
# catalog content and must NOT be flagged here. This snippet receives
# CURRENT_HOME as its first argument.
# ---------------------------------------------------------------------------

SCAN_YAML_HOME_PY='
import sys, yaml

current_home = sys.argv[1] if len(sys.argv) > 1 else ""

def walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = (path + "." + str(k)) if path else str(k)
            walk(v, child)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, path + "[" + str(i) + "]")
    elif isinstance(obj, str):
        if current_home and obj.startswith(current_home):
            sys.stdout.buffer.write(path.encode() + b"\x00" + obj.encode() + b"\x00")

try:
    data = yaml.safe_load(sys.stdin)
    if data is not None:
        walk(data)
except yaml.YAMLError as e:
    sys.stderr.write("ERROR: invalid YAML: " + str(e) + "\n")
    sys.exit(2)
'

# ---------------------------------------------------------------------------
# Check: working-repos.yaml — SOFT warn (current-machine $HOME-rooted only)
# ---------------------------------------------------------------------------

CURRENT_HOME="${HOME:-}"

_check_working_repos_yaml() {
    local file="$1"
    local content

    if [[ -f "$file" ]]; then
        content="$(cat "$file")"
    elif git rev-parse --git-dir >/dev/null 2>&1; then
        content="$(git show ":${file}" 2>/dev/null)" || return
    else
        echo "check-machine-path-leak.sh: WARN — ${file} not found on disk" >&2
        return
    fi

    # Determine if PyYAML is available for structural parsing.
    local pyyaml_ok
    pyyaml_ok="$("$PY3" -c "import yaml; print('yes')" 2>/dev/null)" || pyyaml_ok="no"

    if [[ "$pyyaml_ok" == "yes" ]]; then
        # Structural walk — flag leaf values rooted at CURRENT_HOME only.
        # NUL-separated output written to temp file (NUL bytes are stripped by bash $()).
        local tmp_yaml_viol
        tmp_yaml_viol="$(mktemp 2>/dev/null || echo "/tmp/_cmpL_yaml_viol_$$")"
        local yaml_rc=0
        "$PY3" -c "$SCAN_YAML_HOME_PY" "$CURRENT_HOME" <<< "$content" >"$tmp_yaml_viol" 2>/dev/null \
            || yaml_rc=$?
        if [[ $yaml_rc -ne 0 ]]; then
            rm -f "$tmp_yaml_viol"
            echo "check-machine-path-leak.sh: WARN — could not parse ${file} as YAML; skipping soft check" >&2
            return
        fi

        local leaf_path leaf_val
        while IFS= read -r -d $'\0' leaf_path <&3 && IFS= read -r -d $'\0' leaf_val <&3; do
            echo "WARN: ${file}: leaf '${leaf_path}' contains current-machine home-rooted path" >&2
            echo "  Value : ${leaf_val}" >&2
            echo "  Note  : If this is an intentional catalog entry, no action needed." >&2
            echo "          If newly introduced, consider moving to machine-local registry." >&2
        done 3< "$tmp_yaml_viol"
        rm -f "$tmp_yaml_viol"
    else
        # Fallback: conservative line-scan.
        # Only flag lines where the VALUE portion starts with $CURRENT_HOME.
        # Foreign-machine paths (X:\, /Users/other/) are skipped — intentional Machine-A catalog.
        # WARN: PyYAML absent — working-repos.yaml leak check is best-effort.
        # Limitation: multiline/next-line YAML values will be missed by this scan.
        if [[ -z "$CURRENT_HOME" ]]; then
            return
        fi
        echo "WARN: PyYAML absent — working-repos.yaml leak check is best-effort" >&2
        local lineno=0
        while IFS= read -r line; do
            (( lineno++ )) || true
            # Extract value portion after ": " or leading "- "
            local value_part=""
            if [[ "$line" =~ ^[[:space:]]*-[[:space:]]+(.*) ]]; then
                value_part="${BASH_REMATCH[1]}"
            elif [[ "$line" =~ :[[:space:]]+(.*) ]]; then
                value_part="${BASH_REMATCH[1]}"
            fi
            # Strip inline comments and surrounding quotes
            value_part="${value_part%%#*}"
            value_part="${value_part%"${value_part##*[![:space:]]}"}"   # rtrim
            value_part="${value_part#\'}" ; value_part="${value_part%\'}"
            value_part="${value_part#\"}" ; value_part="${value_part%\"}"

            if [[ -n "$value_part" ]] && [[ "$value_part" == "${CURRENT_HOME}"* ]]; then
                echo "WARN: ${file}:${lineno}: current-machine home-rooted path: ${value_part}" >&2
                echo "  Note  : If this is an intentional catalog entry, no action needed." >&2
                echo "          If newly introduced, consider moving to machine-local registry." >&2
            fi
        done <<< "$content"
    fi
}

for wf in "${WORKING_REPOS_FILES[@]}"; do
    _check_working_repos_yaml "$wf"
done

# ---------------------------------------------------------------------------
# Summary and exit
# ---------------------------------------------------------------------------

TOTAL_FILES=$(( ${#SETTINGS_FILES[@]} + ${#WORKING_REPOS_FILES[@]} ))

if [[ $TOTAL_FILES -eq 0 ]]; then
    echo "OK: no settings.json or working-repos.yaml in scope — nothing to check"
    exit 0
fi

if [[ $HARD_VIOLATION -ne 0 ]]; then
    echo "BLOCKED: machine-path leak detected — commit rejected" >&2
    exit 1
fi

echo "OK: no machine-path leaks detected in ${TOTAL_FILES} file(s)"
exit 0
