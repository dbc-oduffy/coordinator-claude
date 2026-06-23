#!/usr/bin/env bash
# verify-snippet-registry-consistency.sh — sync-of-syncs verifier for snippets/registry.toml.
#
# Confirms that registry.toml is consistent with the 4 HARDCODED-shape verify-<X>-sync.sh scripts.
# Supports two sourcing modes per script:
#   post-migration: script uses `mapfile -t HARDCODED_CONSUMERS < <("$REGISTRY_CLI" list-consumers <name>)`
#   legacy:         script uses a literal `HARDCODED_CONSUMERS=( ... )` array
#
# Post-migration check (C5a-d and later): verifies the snippet name embedded in the mapfile
# call matches one of the 4 enrolled snippets and that no stale literal array coexists.
# Legacy check (pre-migration): set-equality + conditional-consumer parity vs. registry.toml.
#
# Usage:
#   verify-snippet-registry-consistency.sh          Run all checks. Exit 0 on success.
#   verify-snippet-registry-consistency.sh --list   Print one line per check in execution order.
#
# Exit codes:
#   0 — all checks pass
#   1 — consistency violation (printed to stderr)
#   2 — missing dep or file not found
#   3 — schema_version mismatch in registry.toml
#
# Checks performed (in order):
#   1. schema_version ∈ {1, 2} in registry.toml (exit 3 on unknown/higher version)
#   2. registry.toml and all 4 verify-X-sync.sh scripts exist on disk (exit 2 if absent)
#   3. bash -n parse check on each of the 4 verify-X-sync.sh scripts (exit 1 on parse error)
#   4. Per script mode detection (post-migration | legacy | broken → exit 1 on broken)
#   5. post-migration: snippet name in mapfile call matches enrolled snippet; no stale literal
#   6. legacy: set-equality of flat consumers (registry vs. script array)
#   7. legacy: conditional-consumer parity (registry vs. script holodeck block)
#
# Spec backlinks:
#   - docs/plans/2026-06-15-snippet-sync-consumer-registry.md § Dispatch Ledger C4, C8
#   - docs/decisions/2026-06-15-snippet-registry-shape.md § Schema amendments — the Staff Engineer C2

# ---------------------------------------------------------------------------
# Bash 4 guard — bash 3.2 (macOS stock) is explicitly unsupported (DR-148).
# This guard MUST be syntactically valid bash 3.2 even though it cannot run there.
# ---------------------------------------------------------------------------
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
    echo "ERROR: verify-snippet-registry-consistency.sh requires bash 4+; got bash ${BASH_VERSION}" >&2
    echo "       macOS: brew install bash && ensure /usr/local/bin or /opt/homebrew/bin precedes /bin in PATH" >&2
    exit 2
fi

set -euo pipefail

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: neither python3 nor python found on PATH" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

REGISTRY_TOML="$PLUGIN_ROOT/snippets/registry.toml"

# Map: snippet name -> relative path of the verify-<X>-sync.sh script (relative to $PLUGIN_ROOT/bin)
# These are the 4 HARDCODED-shape scripts enrolled in the registry.
declare -A VERIFY_SCRIPTS
VERIFY_SCRIPTS["reviewer-calibration"]="verify-calibration-sync.sh"
VERIFY_SCRIPTS["docs-checker-consumption"]="verify-docs-checker-sync.sh"
VERIFY_SCRIPTS["plan-coverage-check-consumption"]="verify-plan-coverage-sync.sh"
VERIFY_SCRIPTS["prior-art-check-consumption"]="verify-prior-art-sync.sh"

# Ordered list for deterministic output
SNIPPET_NAMES=(
    "reviewer-calibration"
    "docs-checker-consumption"
    "plan-coverage-check-consumption"
    "prior-art-check-consumption"
)

# ---------------------------------------------------------------------------
# --list mode: print checks in execution order, then exit
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--list" ]; then
    # Review: code-reviewer F6 — document that schema_version exits 3 on mismatch (not surfaced otherwise in --list)
    echo "check:schema_version — registry.toml schema_version ∈ {1,2} (exit 3 on unknown/higher version)"
    echo "check:registry_exists — registry.toml exists on disk"
    for name in "${SNIPPET_NAMES[@]}"; do
        script="${VERIFY_SCRIPTS[$name]}"
        echo "check:verify_script_exists[$name] — bin/$script exists on disk"
    done
    for name in "${SNIPPET_NAMES[@]}"; do
        script="${VERIFY_SCRIPTS[$name]}"
        echo "check:bash_n[$name] — bash -n bin/$script (parse check)"
    done
    for name in "${SNIPPET_NAMES[@]}"; do
        echo "check:mode_detect[$name] — detect sourcing mode (post-migration mapfile | legacy literal | broken)"
        echo "check:post_migration[$name] — (post-migration) snippet name in mapfile matches enrolled; no stale literal array"
        echo "check:set_equality[$name] — (legacy only) flat consumers: registry.toml vs. HARDCODED_CONSUMERS in verify script"
        echo "check:conditional_parity[$name] — (legacy only) conditional consumers: registry.toml vs. holodeck block in verify script"
    done
    exit 0
fi

# Guard: no unknown subcommands
if [ $# -gt 0 ] && [ "${1}" != "--list" ]; then
    echo "ERROR: unknown argument '${1}'" >&2
    echo "Usage: $(basename "$0") [--list]" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Python helper: parse registry.toml and emit check data.
# Uses stdlib tomllib (Python 3.11+) or tomli fallback (3.8-3.10).
# Outputs lines of the form:
#   SCHEMA_VERSION <n>
#   CONSUMER <snippet_name> <absolute_path>
#   COND_PATH <snippet_name> <relative_path_in_condition_root>
#   COND_KEY <snippet_name> <condition_key>
#   ERROR <message>
# ---------------------------------------------------------------------------
# Strip \r so Python's Windows CRLF output doesn't corrupt bash variable comparisons.
PARSE_OUTPUT="$("$PYTHON_BIN" - "$REGISTRY_TOML" "$PLUGIN_ROOT" <<'PYEOF' | tr -d '\r'
import sys
import os

registry_path = sys.argv[1]
plugin_root   = sys.argv[2]

try:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            # Python < 3.11 without tomli: use a minimal inline TOML parser
            # restricted to what registry.toml actually uses (string/int scalars
            # and array-of-tables). Not a general TOML parser.
            tomllib = None

    if tomllib is None:
        # Minimal inline parser sufficient for registry.toml shape.
        # Handles: key = value, key = [ ... ], [[section.sub]], [section]
        import re

        def parse_registry_toml(text):
            """Parse registry.toml into a dict matching tomllib output shape."""
            lines = text.splitlines()
            result = {"schema_version": None, "snippet": {}}
            current_snippet = None
            current_cond = None
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                # Skip blank lines and comments
                if not line or line.startswith("#"):
                    i += 1
                    continue
                # [[snippet.<name>.conditional_consumer]] — array-of-tables entry
                m = re.match(r'^\[\[snippet\.([^.]+)\.conditional_consumer\]\]$', line)
                if m:
                    sname = m.group(1)
                    if sname not in result["snippet"]:
                        result["snippet"][sname] = {}
                    if "conditional_consumer" not in result["snippet"][sname]:
                        result["snippet"][sname]["conditional_consumer"] = []
                    current_cond = {}
                    result["snippet"][sname]["conditional_consumer"].append(current_cond)
                    current_snippet = sname
                    i += 1
                    continue
                # [snippet.<name>] — table entry
                m = re.match(r'^\[snippet\.([^]]+)\]$', line)
                if m:
                    sname = m.group(1)
                    if sname not in result["snippet"]:
                        result["snippet"][sname] = {}
                    current_snippet = sname
                    current_cond = None
                    i += 1
                    continue
                # schema_version = N at root
                m = re.match(r'^schema_version\s*=\s*(\d+)$', line)
                if m:
                    result["schema_version"] = int(m.group(1))
                    i += 1
                    continue
                # key = "value" (single-line string)
                m = re.match(r'^(\w+)\s*=\s*"(.*)"$', line)
                if m:
                    k, v = m.group(1), m.group(2)
                    if current_cond is not None:
                        current_cond[k] = v
                    elif current_snippet is not None:
                        result["snippet"][current_snippet][k] = v
                    i += 1
                    continue
                # consumers = [ ... ] — may span multiple lines
                m = re.match(r'^consumers\s*=\s*\[', line)
                if m:
                    # Collect until closing ]
                    # Review: code-reviewer F4 — add EOF bounds-check; unclosed array at EOF
                    # previously raised IndexError swallowed by outer except with cryptic message.
                    bracket_line = line
                    while "]" not in bracket_line[bracket_line.index("[") + 1:]:
                        i += 1
                        if i >= len(lines):
                            print("ERROR unclosed consumers array in registry.toml")
                            sys.exit(1)
                        bracket_line += " " + lines[i].strip()
                    # Extract quoted strings
                    vals = re.findall(r'"([^"]*)"', bracket_line)
                    if current_snippet is not None:
                        result["snippet"][current_snippet]["consumers"] = vals
                    i += 1
                    continue
                # Review: code-reviewer F8 — fail loud on unrecognized non-blank/non-comment lines
                # rather than silently skipping; future TOML fields with subtle syntax would parse
                # wrong without any diagnostic.
                print(f"ERROR unrecognized line in registry.toml: {line!r}")
                sys.exit(1)
            return result

        with open(registry_path, "r", encoding="utf-8") as f:
            text = f.read()
        data = parse_registry_toml(text)
    else:
        with open(registry_path, "rb") as f:
            data = tomllib.load(f)

    # Emit schema_version
    sv = data.get("schema_version")
    if sv is None:
        print("ERROR schema_version field missing from registry.toml")
        # Review: logic-slice L-F1 — exit 3 (not 0) to match CLI contract (sys.exit(3) for
        # schema_version problems) and the documented exit-code table in the file header.
        sys.exit(3)
    print(f"SCHEMA_VERSION {sv}")

    # Emit consumers and conditionals per snippet
    snippets = data.get("snippet", {})
    for sname, sdata in snippets.items():
        consumers = sdata.get("consumers", [])
        for rel_path in consumers:
            if rel_path.startswith("../"):
                # sibling plugin: resolve relative to PLUGIN_ROOT/..
                abs_path = os.path.normpath(os.path.join(plugin_root, rel_path))
            else:
                abs_path = os.path.normpath(os.path.join(plugin_root, rel_path))
            print(f"CONSUMER {sname} {abs_path}")

        cond_consumers = sdata.get("conditional_consumer", [])
        # Review: code-reviewer F11 — document alternating-pair invariant: for each conditional_consumer
        # entry, COND_PATH is emitted immediately followed by COND_KEY for the SAME entry/snippet.
        # Bash consumers correlate them by position in parallel lists. If this loop order changes,
        # the bash parser at case "COND_PATH"/"COND_KEY" (second pass) will desynchronize.
        # Review: code-reviewer F12 — normalize COND_KEY to single-space delimiter (was two spaces),
        # matching all other token formats and preventing silent parse breakage on maintainer normalization.
        for cond in cond_consumers:
            cpath = cond.get("path", "")
            ckey  = cond.get("condition_key", "")
            print(f"COND_PATH {sname} {cpath}")
            # Review: logic-slice L-F3 — only emit COND_KEY when ckey is non-empty;
            # file-exists entries have no condition_key, and an unconditional emit pollutes
            # REGISTRY_COND_KEYS with empty entries that corrupt the condition_key parity check.
            if ckey:
                print(f"COND_KEY {sname} {ckey}")

except FileNotFoundError:
    print(f"ERROR registry.toml not found: {registry_path}")
except Exception as e:
    print(f"ERROR {e}")
PYEOF
)"

# ---------------------------------------------------------------------------
# Check: registry.toml exists + parse output
# ---------------------------------------------------------------------------
OVERALL_EXIT=0

if [ ! -f "$REGISTRY_TOML" ]; then
    echo "ERROR: registry.toml not found at $REGISTRY_TOML" >&2
    exit 2
fi

# Check for parse errors from Python
while IFS= read -r line; do
    case "$line" in
        "ERROR "*)
            echo "ERROR: registry.toml parse failed: ${line#ERROR }" >&2
            exit 2
            ;;
    esac
done <<< "$PARSE_OUTPUT"

# ---------------------------------------------------------------------------
# Check: schema_version
# ---------------------------------------------------------------------------
SCHEMA_VER="$(grep '^SCHEMA_VERSION ' <<< "$PARSE_OUTPUT" | awk '{print $2}' || true)"
if [ -z "$SCHEMA_VER" ]; then
    echo "ERROR: verify-snippet-registry-consistency: schema_version field missing from registry.toml" >&2
    exit 3
fi
# Review: logic-slice L-F7 — Enumerated allowlist, not arithmetic — a non-integer version must also fail-loud.
if [ "$SCHEMA_VER" != "1" ] && [ "$SCHEMA_VER" != "2" ]; then
    echo "ERROR: verify-snippet-registry-consistency: unknown schema_version (supports up to 2, got ${SCHEMA_VER})" >&2
    exit 3
fi

# ---------------------------------------------------------------------------
# Check: all 4 verify-X-sync.sh scripts exist
# ---------------------------------------------------------------------------
for name in "${SNIPPET_NAMES[@]}"; do
    script_path="$PLUGIN_ROOT/bin/${VERIFY_SCRIPTS[$name]}"
    if [ ! -f "$script_path" ]; then
        echo "ERROR: verify script not found: $script_path" >&2
        exit 2
    fi
done

# ---------------------------------------------------------------------------
# Check: bash -n parse check on each verify script
# ---------------------------------------------------------------------------
for name in "${SNIPPET_NAMES[@]}"; do
    script_path="$PLUGIN_ROOT/bin/${VERIFY_SCRIPTS[$name]}"
    if ! bash -n "$script_path" 2>/dev/null; then
        echo "FAIL [bash-n] $script_path: parse error" >&2
        bash -n "$script_path" >&2 || true
        OVERALL_EXIT=1
    fi
done

# ---------------------------------------------------------------------------
# Build sets from registry.toml parse output
# ---------------------------------------------------------------------------
# Associative arrays: REGISTRY_CONSUMERS[snippet_name] = newline-separated absolute paths (sorted)
# REGISTRY_COND_PATHS[snippet_name] = newline-separated "condpath|condkey" pairs (sorted)
declare -A REGISTRY_CONSUMERS
declare -A REGISTRY_COND_PATHS

for name in "${SNIPPET_NAMES[@]}"; do
    REGISTRY_CONSUMERS[$name]=""
    REGISTRY_COND_PATHS[$name]=""
done

while IFS= read -r line; do
    case "$line" in
        "CONSUMER "*)
            rest="${line#CONSUMER }"
            sname="${rest%% *}"
            apath="${rest#* }"
            if [ -n "${REGISTRY_CONSUMERS[$sname]+_}" ]; then
                if [ -n "${REGISTRY_CONSUMERS[$sname]}" ]; then
                    REGISTRY_CONSUMERS[$sname]="${REGISTRY_CONSUMERS[$sname]}"$'\n'"${apath}"
                else
                    REGISTRY_CONSUMERS[$sname]="${apath}"
                fi
            fi
            ;;
    esac
done <<< "$PARSE_OUTPUT"
# Review: code-reviewer F1 — dead COND_PATH branch in first loop discarded cpath without use;
# COND_PATH is correctly accumulated by the second loop below. Removed dead branch.

# Build (cond_path|cond_key) pairs per snippet
while IFS= read -r line; do
    case "$line" in
        "COND_PATH "*)
            rest="${line#COND_PATH }"
            sname="${rest%% *}"
            cpath="${rest#* }"
            # peek at next COND_KEY line — stored in parallel; we correlate by order
            if [ -n "${REGISTRY_COND_PATHS[$sname]+_}" ]; then
                if [ -n "${REGISTRY_COND_PATHS[$sname]}" ]; then
                    REGISTRY_COND_PATHS[$sname]="${REGISTRY_COND_PATHS[$sname]}"$'\n'"${cpath}"
                else
                    REGISTRY_COND_PATHS[$sname]="${cpath}"
                fi
            fi
            ;;
    esac
done <<< "$PARSE_OUTPUT"

# Also build cond_key sets per snippet (parallel to cond_path sets)
declare -A REGISTRY_COND_KEYS
for name in "${SNIPPET_NAMES[@]}"; do
    REGISTRY_COND_KEYS[$name]=""
done
while IFS= read -r line; do
    case "$line" in
        # Review: code-reviewer F12 — normalized from two-space "COND_KEY  " to single-space "COND_KEY "
        # matching the emitter change; maintainer normalization no longer silently breaks parsing.
        "COND_KEY "*)
            rest="${line#COND_KEY }"
            sname="${rest%% *}"
            ckey="${rest#* }"
            if [ -n "${REGISTRY_COND_KEYS[$sname]+_}" ]; then
                if [ -n "${REGISTRY_COND_KEYS[$sname]}" ]; then
                    REGISTRY_COND_KEYS[$sname]="${REGISTRY_COND_KEYS[$sname]}"$'\n'"${ckey}"
                else
                    REGISTRY_COND_KEYS[$sname]="${ckey}"
                fi
            fi
            ;;
    esac
done <<< "$PARSE_OUTPUT"

# ---------------------------------------------------------------------------
# detect_script_mode: determine how a verify-X-sync.sh script sources its consumer list.
#
# Outputs one of:
#   MODE post-migration <snippet_name>   — uses mapfile -t HARDCODED_CONSUMERS < <("$REGISTRY_CLI" list-consumers <name>)
#   MODE legacy                          — uses literal HARDCODED_CONSUMERS=( ... ) array
#   MODE broken                          — neither pattern present (exit 1 upstream)
# ---------------------------------------------------------------------------
detect_script_mode() {
    local script_path="$1"

    "$PYTHON_BIN" - "$script_path" <<'PYEOF' | tr -d '\r'
import sys
import re

script_path = sys.argv[1]

with open(script_path, "r", encoding="utf-8") as f:
    content = f.read()

# Post-migration pattern: mapfile -t HARDCODED_CONSUMERS < <("$REGISTRY_CLI" list-consumers <name>)
# Allow either $REGISTRY_CLI or ${REGISTRY_CLI}
m = re.search(
    r'mapfile\s+-t\s+HARDCODED_CONSUMERS\s+<\s+<\(\s*["\']?\$\{?REGISTRY_CLI\}?["\']?\s+list-consumers\s+([\w\-]+)\s*\)',
    content
)
if m:
    snippet_name = m.group(1)
    print(f"MODE post-migration {snippet_name}")
    sys.exit(0)

# Legacy pattern: literal HARDCODED_CONSUMERS=( ... )
if re.search(r'HARDCODED_CONSUMERS\s*=\s*\(', content):
    print("MODE legacy")
    sys.exit(0)

print("MODE broken")
PYEOF
}

# ---------------------------------------------------------------------------
# Extract consumers from a legacy verify-X-sync.sh via Python parsing.
# Used only when detect_script_mode reports "legacy".
# ---------------------------------------------------------------------------
extract_script_consumers_legacy() {
    local script_path="$1"
    local plugin_root="$2"

    "$PYTHON_BIN" - "$script_path" "$plugin_root" <<'PYEOF' | tr -d '\r'
import sys
import re
import os

script_path = sys.argv[1]
plugin_root = sys.argv[2]

with open(script_path, "r", encoding="utf-8") as f:
    content = f.read()

# Extract the HARDCODED_CONSUMERS=( ... ) block — may span multiple lines.
m = re.search(r'HARDCODED_CONSUMERS=\(\s*(.*?)\)', content, re.DOTALL)
if not m:
    print("ERROR no HARDCODED_CONSUMERS array found")
    sys.exit(1)

array_body = m.group(1)

# Extract quoted strings from the array body.
entries = re.findall(r'"([^"]*)"', array_body)

# Resolve $PLUGIN_ROOT references
# Review: code-reviewer F5 — also handle ${PLUGIN_ROOT} brace form; assert no residual after replace.
resolved = []
for e in entries:
    if "$PLUGIN_ROOT" in e or "${PLUGIN_ROOT}" in e:
        rel = e.replace("${PLUGIN_ROOT}", plugin_root).replace("$PLUGIN_ROOT", plugin_root)
        if "$PLUGIN_ROOT" in rel:
            print(f"ERROR $PLUGIN_ROOT replacement failed for entry: {e!r}")
            sys.exit(1)
        abs_path = os.path.normpath(rel)
        resolved.append(abs_path)
    else:
        resolved.append(e)

for p in resolved:
    print(f"FLAT {p}")

# Extract conditional holodeck consumers: look for HARDCODED_CONSUMERS+=("$_HOLODECK_ROOT/<path>")
cond_entries = re.findall(r'HARDCODED_CONSUMERS\+=\("?\$_HOLODECK_ROOT/([^")]+)"?\)', content)
for cpath in cond_entries:
    print(f"COND {cpath}")

# Detect which condition_key is used (the script uses repos.claude_unreal_holodeck)
if 'repos.claude_unreal_holodeck' in content:
    print("COND_KEY repos.claude_unreal_holodeck")
PYEOF
}

# ---------------------------------------------------------------------------
# check_post_migration_script: verify a post-migration verify script is consistent.
#   1. snippet name from mapfile call matches the expected enrolled snippet name.
#   2. no stale literal HARDCODED_CONSUMERS=( ... ) array coexists.
# ---------------------------------------------------------------------------
check_post_migration_script() {
    local script_path="$1"
    local expected_snippet="$2"   # the snippet name this script is enrolled under
    local detected_snippet="$3"   # the name extracted from the mapfile call

    local ok=0

    # Check 1: snippet name matches
    if [ "$detected_snippet" != "$expected_snippet" ]; then
        echo "FAIL [post-migration] $script_path: mapfile calls list-consumers '$detected_snippet' but expected '$expected_snippet'" >&2
        ok=1
    fi

    # Check 2: no stale literal array
    # Review: code-reviewer F3 — \s is GNU-only; BSD grep (macOS) silently mismatch. Use literal form.
    if grep -q 'HARDCODED_CONSUMERS=(' "$script_path" 2>/dev/null; then
        echo "FAIL [post-migration] $script_path: stale literal HARDCODED_CONSUMERS=( ... ) array still present — migration incomplete" >&2
        ok=1
    fi

    return "$ok"
}

# ---------------------------------------------------------------------------
# Set-equality comparison: registry consumers vs. script HARDCODED_CONSUMERS
# ---------------------------------------------------------------------------
sort_set() {
    # Sort a newline-separated list; remove blanks
    printf '%s\n' "$1" | grep -v '^$' | sort
}

compare_sets() {
    local label="$1"
    local set_a="$2"   # from registry (sorted)
    local set_b="$3"   # from script (sorted)

    local sorted_a sorted_b diff_out
    sorted_a="$(sort_set "$set_a")"
    sorted_b="$(sort_set "$set_b")"

    if [ "$sorted_a" = "$sorted_b" ]; then
        return 0
    fi

    # Report differences
    # Review: code-reviewer F7 — sort_set already strips blanks; grep -v '^$' here was redundant.
    local missing_from_registry missing_from_script
    missing_from_registry="$(comm -13 <(printf '%s\n' "$sorted_a") <(printf '%s\n' "$sorted_b") || true)"
    missing_from_script="$(comm -23 <(printf '%s\n' "$sorted_a") <(printf '%s\n' "$sorted_b") || true)"

    if [ -n "$missing_from_registry" ]; then
        echo "FAIL [set-equality] $label: paths in script but missing from registry:" >&2
        while IFS= read -r p; do
            [ -n "$p" ] && echo "  missing-from-registry: $p" >&2
        done <<< "$missing_from_registry"
    fi
    if [ -n "$missing_from_script" ]; then
        echo "FAIL [set-equality] $label: paths in registry but missing from script:" >&2
        while IFS= read -r p; do
            [ -n "$p" ] && echo "  missing-from-script: $p" >&2
        done <<< "$missing_from_script"
    fi
    return 1
}

# ---------------------------------------------------------------------------
# Main check loop: per-snippet consistency (mode-aware)
# ---------------------------------------------------------------------------
for name in "${SNIPPET_NAMES[@]}"; do
    script_path="$PLUGIN_ROOT/bin/${VERIFY_SCRIPTS[$name]}"

    # --- Detect sourcing mode ---
    MODE_LINE="$(detect_script_mode "$script_path" | tr -d '\r')"
    SCRIPT_MODE="${MODE_LINE#MODE }"   # strip "MODE " prefix
    SCRIPT_MODE_TYPE="${SCRIPT_MODE%% *}"  # first word: post-migration | legacy | broken

    if [ "$SCRIPT_MODE_TYPE" = "broken" ]; then
        echo "FAIL [mode-detect] $name ($script_path): neither post-migration mapfile pattern nor legacy literal array found" >&2
        OVERALL_EXIT=1
        continue
    fi

    if [ "$SCRIPT_MODE_TYPE" = "post-migration" ]; then
        # --- Post-migration checks ---
        DETECTED_SNIPPET="${SCRIPT_MODE#post-migration }"
        if ! check_post_migration_script "$script_path" "$name" "$DETECTED_SNIPPET"; then
            OVERALL_EXIT=1
        fi
        # No set-equality or conditional-parity checks needed: the script delegates
        # consumer resolution to the registry CLI, which IS the registry. Consistency
        # is structural (they use the same source of truth).
        continue
    fi

    # --- Legacy checks (script still has a literal HARDCODED_CONSUMERS array) ---
    SCRIPT_PARSE="$(extract_script_consumers_legacy "$script_path" "$PLUGIN_ROOT")"

    # Check for parser errors
    if grep -q '^ERROR ' <<< "$SCRIPT_PARSE" 2>/dev/null; then
        echo "FAIL [script-parse] $name: $(grep '^ERROR ' <<< "$SCRIPT_PARSE")" >&2
        OVERALL_EXIT=1
        continue
    fi

    # Build script flat consumer set (absolute paths)
    SCRIPT_FLAT_CONSUMERS=""
    while IFS= read -r line; do
        case "$line" in
            "FLAT "*)
                p="${line#FLAT }"
                if [ -n "$SCRIPT_FLAT_CONSUMERS" ]; then
                    SCRIPT_FLAT_CONSUMERS="${SCRIPT_FLAT_CONSUMERS}"$'\n'"${p}"
                else
                    SCRIPT_FLAT_CONSUMERS="${p}"
                fi
                ;;
        esac
    done <<< "$SCRIPT_PARSE"

    # Build script conditional paths (relative to holodeck root)
    SCRIPT_COND_PATHS=""
    while IFS= read -r line; do
        case "$line" in
            "COND "*)
                cpath="${line#COND }"
                if [ -n "$SCRIPT_COND_PATHS" ]; then
                    SCRIPT_COND_PATHS="${SCRIPT_COND_PATHS}"$'\n'"${cpath}"
                else
                    SCRIPT_COND_PATHS="${cpath}"
                fi
                ;;
        esac
    done <<< "$SCRIPT_PARSE"

    # --- Check: set-equality of flat consumers ---
    if ! compare_sets "$name (flat consumers)" "${REGISTRY_CONSUMERS[$name]}" "$SCRIPT_FLAT_CONSUMERS"; then
        OVERALL_EXIT=1
    fi

    # --- Check: conditional-consumer parity ---
    REG_COND="${REGISTRY_COND_PATHS[$name]}"
    SCR_COND="$SCRIPT_COND_PATHS"

    sorted_reg_cond="$(sort_set "$REG_COND")"
    sorted_scr_cond="$(sort_set "$SCR_COND")"

    if [ "$sorted_reg_cond" != "$sorted_scr_cond" ]; then
        MISSING_FROM_REG="$(comm -13 <(printf '%s\n' "$sorted_reg_cond" | grep -v '^$') <(printf '%s\n' "$sorted_scr_cond" | grep -v '^$') || true)"
        MISSING_FROM_SCR="$(comm -23 <(printf '%s\n' "$sorted_reg_cond" | grep -v '^$') <(printf '%s\n' "$sorted_scr_cond" | grep -v '^$') || true)"
        if [ -n "$MISSING_FROM_REG" ]; then
            echo "FAIL [conditional-parity] $name: holodeck paths in script but missing from registry conditional_consumer:" >&2
            while IFS= read -r p; do
                [ -n "$p" ] && echo "  missing-from-registry: $p" >&2
            done <<< "$MISSING_FROM_REG"
        fi
        if [ -n "$MISSING_FROM_SCR" ]; then
            echo "FAIL [conditional-parity] $name: holodeck paths in registry conditional_consumer but missing from script:" >&2
            while IFS= read -r p; do
                [ -n "$p" ] && echo "  missing-from-script: $p" >&2
            done <<< "$MISSING_FROM_SCR"
        fi
        OVERALL_EXIT=1
    fi

    # Verify condition_key consistency for holodeck conditionals
    # Review: code-reviewer F2 — check fires whenever registry has conditional_consumer entries
    # (REG_COND non-empty), not only when the script has a holodeck conditional (SCR_COND).
    # Previously, a registry entry with a malformed condition_key AND no script holodeck block
    # would pass unchecked.
    #
    # Awareness note (2026-06-19, schema v2 file-exists migration): this legacy parity block is
    # MOOT today — all 4 verify scripts are post-migration (mapfile from the CLI), so the
    # per-snippet loop reaches here only for legacy-mode scripts, of which there are none. The
    # `[ -z "$ckey" ] && continue` below already skips file-exists entries (empty condition_key),
    # so the condition_key assertion is file-exists-safe. The residual exposure is a FUTURE
    # legacy revert: a script reverted to legacy mode would mismatch the file-exists paths at the
    # set-equality check above (655) and FAIL. This is unprotected by design — legacy mode assumes
    # the machine-local-key shape and is being retired, not extended. If a legacy revert is ever
    # contemplated, make the set-equality + parity logic condition_type-aware first.
    REG_KEYS="${REGISTRY_COND_KEYS[$name]}"
    if [ -n "$REG_COND" ]; then
        if [ -z "$SCR_COND" ]; then
            echo "FAIL [conditional-parity] $name: registry has conditional_consumer entries but script has none" >&2
            OVERALL_EXIT=1
        fi
        while IFS= read -r ckey; do
            [ -z "$ckey" ] && continue
            if [ "$ckey" != "repos.claude_unreal_holodeck" ]; then
                echo "FAIL [conditional-parity] $name: unexpected condition_key in registry: '$ckey'" >&2
                OVERALL_EXIT=1
            fi
        done <<< "$REG_KEYS"
    elif [ -n "$SCR_COND" ]; then
        echo "FAIL [conditional-parity] $name: script has holodeck conditional consumer but registry has none" >&2
        OVERALL_EXIT=1
    fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [ "$OVERALL_EXIT" -eq 0 ]; then
    echo "OK: registry.toml is consistent with all 4 verify scripts (mode-aware: post-migration scripts verified via mapfile-call name match; legacy scripts verified via set-equality)"
fi

exit "$OVERALL_EXIT"
