#!/usr/bin/env bash
# lib/coordinator-currency.sh — Per-repo coordinator currency stamp: write + read + probe.
#
# Purpose: records and checks which COORDINATOR_SCHEMA_VERSION a project's scaffolding was
# onboarded (or last refreshed) against. Consumed by /project-onboarding (stamp write),
# the doctor probe P-13, and Wave-2 Chunk 3 (command-invocation-time currency detector).
#
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1
#
# Compose-vs-invent decision (recorded here per spec): the existing version.txt sentinel
# (agentic-install-integrity.md §3) is a git-SHA anchoring the PLUGIN live-install to a
# source HEAD — it is a byte-divergence classifier anchor, not a schema version.
# check-plugin-drift.sh compares plugin-install vs plugin-source; it has no concept of
# "consumer project was onboarded against schema version N." These primitives are
# orthogonal. A new per-repo stamp (coordinator-currency.yaml) is therefore required.
# It is kept separate from coordinator-setup-state.yaml whose set-once/never-overwritten
# contract is architecturally load-bearing.
#
# Stamp location (per-repo): docs/coordinator-currency.yaml
# Schema version source:      <plugin-root>/coordinator-schema-version  (single integer line)
#
# Public API:
#   coordinator_currency_write  <repo_root> <plugin_root>   — idempotent stamp write
#   coordinator_currency_read   <repo_root>                 — prints stamped version (int) or ""
#   coordinator_currency_probe  <repo_root> <plugin_root>   — prints status string + exits 0
#
# Exit codes for coordinator_currency_probe:
#   0 — always (probe is read-only; status communicated via stdout)
#
# Status strings (stdout):
#   current              — stamp present, matches live COORDINATOR_SCHEMA_VERSION
#   drift(N->M)          — stamp present, version older than current (N=stamped, M=current)
#   unstamped(legacy)    — probe ran, no stamp found; repo predates currency feature    [AMBER]
#   inconclusive(<msg>)  — probe could not determine status; reason in parens            [AMBER]
#
# source_is_live note: on machines where the live install IS the source (~/.claude), a
# missing stamp is EXPECTED — the probe treats source_is_live repos as structural no-ops
# (mirrors check-plugin-drift.sh behaviour). This is not inconclusive.

set -uo pipefail

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# _currency_stamp_path <repo_root> → prints the stamp file path
_currency_stamp_path() {
    local repo_root="${1:?repo_root required}"
    printf '%s/docs/coordinator-currency.yaml' "$repo_root"
}

# _read_schema_version <plugin_root> → prints integer version or "" on failure
_read_schema_version() {
    local plugin_root="${1:?plugin_root required}"
    local ver_file="${plugin_root}/coordinator-schema-version"
    if [[ ! -f "$ver_file" ]]; then
        return 1
    fi
    local ver
    ver="$(tr -d '[:space:]' < "$ver_file")"
    # Must be a positive integer
    if [[ "$ver" =~ ^[1-9][0-9]*$ ]]; then
        printf '%s' "$ver"
    else
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Public: coordinator_currency_write
# ---------------------------------------------------------------------------
# Idempotent: if stamp already exists with the SAME version, no-op (exits 0, no file change).
# If stamp exists with a DIFFERENT version, overwrites (refresh after plugin upgrade).
# Always writes docs/ directory first if absent.
#
# Arguments:
#   $1 — repo_root   (absolute path to the project repo being stamped)
#   $2 — plugin_root (absolute path to the coordinator plugin root, e.g. ~/.claude/plugins/...)
coordinator_currency_write() {
    local repo_root="${1:?repo_root required}"
    local plugin_root="${2:?plugin_root required}"

    local current_version
    current_version="$(_read_schema_version "$plugin_root")" || {
        echo "coordinator_currency_write: cannot read COORDINATOR_SCHEMA_VERSION from '${plugin_root}/coordinator-schema-version'" >&2
        return 1
    }

    local stamp_path
    stamp_path="$(_currency_stamp_path "$repo_root")"
    local stamp_dir
    stamp_dir="$(dirname "$stamp_path")"

    # Idempotency check — if stamp exists and version matches, no-op
    if [[ -f "$stamp_path" ]]; then
        local existing_version
        existing_version="$(coordinator_currency_read "$repo_root" 2>/dev/null)" || true
        if [[ "$existing_version" == "$current_version" ]]; then
            # Already current — no file change
            return 0
        fi
    fi

    # Ensure docs/ directory exists
    if [[ ! -d "$stamp_dir" ]]; then
        mkdir -p "$stamp_dir" || {
            echo "coordinator_currency_write: failed to create directory '${stamp_dir}'" >&2
            return 1
        }
    fi

    local stamp_date
    stamp_date="$(date -u +%Y-%m-%d 2>/dev/null || echo "unknown")"

    # Write via temp file + atomic mv to guard against partial-write on failure.
    # set -uo pipefail does NOT propagate through here-doc writes inside a sourced
    # function without -e; explicit exit-code capture is required.
    local tmp_path
    tmp_path="${stamp_path}.tmp.$$"

    cat > "$tmp_path" <<EOF
# coordinator-currency.yaml — per-repo coordinator schema currency stamp.
#
# Written by: coordinator_currency_write (lib/coordinator-currency.sh)
# Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1
#
# MUTABLE — updated on refresh. Separate from coordinator-setup-state.yaml (set-once).
# Read by: doctor probe P-13, Wave-2 Chunk 3 currency detector.
schema_version: ${current_version}
stamped_at: ${stamp_date}
EOF
    local cat_exit=$?
    if [[ $cat_exit -ne 0 ]]; then
        rm -f "$tmp_path" 2>/dev/null || true
        echo "coordinator_currency_write: failed to write temp stamp file '${tmp_path}'" >&2
        return 1
    fi

    if ! mv "$tmp_path" "$stamp_path" 2>/dev/null; then
        rm -f "$tmp_path" 2>/dev/null || true
        echo "coordinator_currency_write: failed to move temp stamp to '${stamp_path}'" >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Public: coordinator_currency_read
# ---------------------------------------------------------------------------
# Reads the stamped schema_version integer from the repo's stamp file.
# Prints the integer to stdout. Exits 1 if stamp absent or unparseable.
coordinator_currency_read() {
    local repo_root="${1:?repo_root required}"
    local stamp_path
    stamp_path="$(_currency_stamp_path "$repo_root")"

    if [[ ! -f "$stamp_path" ]]; then
        return 1
    fi

    local ver
    ver="$(grep -E '^schema_version:' "$stamp_path" | head -1 | sed 's/schema_version:[[:space:]]*//' | tr -d '[:space:]')"
    if [[ "$ver" =~ ^[1-9][0-9]*$ ]]; then
        printf '%s' "$ver"
    else
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Public: coordinator_currency_probe
# ---------------------------------------------------------------------------
# Read-only. Always exits 0. Prints one status string to stdout.
# Caller interprets GREEN/AMBER from the string prefix.
coordinator_currency_probe() {
    local repo_root="${1:?repo_root required}"
    local plugin_root="${2:?plugin_root required}"

    # Resolve current schema version
    local current_version
    if ! current_version="$(_read_schema_version "$plugin_root")"; then
        printf 'inconclusive(schema constant unreadable: %s/coordinator-schema-version missing or malformed)' "$plugin_root"
        return 0
    fi

    local stamp_path
    stamp_path="$(_currency_stamp_path "$repo_root")"

    if [[ ! -f "$stamp_path" ]]; then
        printf 'unstamped(legacy)'
        return 0
    fi

    local stamped_version
    if ! stamped_version="$(coordinator_currency_read "$repo_root")"; then
        printf 'inconclusive(stamp present but schema_version unparseable: %s)' "$stamp_path"
        return 0
    fi

    if [[ "$stamped_version" == "$current_version" ]]; then
        printf 'current'
    elif [[ "$stamped_version" -lt "$current_version" ]] 2>/dev/null; then
        printf 'drift(%s->%s)' "$stamped_version" "$current_version"
    else
        # stamped_version > current_version — future stamp, treat as inconclusive
        printf 'inconclusive(stamped version %s > current version %s; probe cannot validate forward stamps)' \
            "$stamped_version" "$current_version"
    fi
    return 0
}
