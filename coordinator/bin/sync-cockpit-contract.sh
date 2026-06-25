#!/usr/bin/env bash
# bin/sync-cockpit-contract.sh — Vendor-sync staleness check for the cockpit-contract JSON Schema.
#
# Purpose: consumer-invocable precondition check that detects version DRIFT between the
# canonical cockpit-contract schema (authored here, under cockpit-contract/schema/) and a
# vendored copy in a consumer repo (e.g. project-opticon at contract/schema/).
#
# Designed to be run BEFORE a re-vendor: if drift is detected the consumer knows to pull the
# latest schema/*.json and regenerate (pnpm run contract:gen) before ingesting new snapshots.
# This is the producer-side half of the vendor-sync safety gate (tc-1 R5 / the Director of Engineering Z-F4);
# the consumer-side half is the ingest-time schema_version assertion in project-opticon
# src/lib/store/ingest.ts (Ask-1).
#
# Spec backlink: state/handoffs/2026-06-22_230001_roadmap-cockpit-contract-ext-2026-06-22-tc-1.md
# § Vendor-sync staleness gate (the Director of Engineering Z-F1/Z-F4).
#
# Usage:
#   sync-cockpit-contract.sh --vendored <path/to/vendored/cockpit-contract.schema.json>
#   sync-cockpit-contract.sh --vendored <path> [--canonical <path>]
#   COCKPIT_CANONICAL=<path> COCKPIT_VENDORED=<path> sync-cockpit-contract.sh
#
# Exit codes:
#   0  — versions match (in sync)
#   1  — DRIFT: versions differ, or vendored copy missing
#   2  — usage / environment error (jq absent, canonical schema missing, bad flags)
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults — overridable by flag or env
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_DEFAULT_CANONICAL="${SCRIPT_DIR}/../cockpit-contract/schema/cockpit-contract.schema.json"

CANONICAL="${COCKPIT_CANONICAL:-${_DEFAULT_CANONICAL}}"
VENDORED="${COCKPIT_VENDORED:-}"

# ---------------------------------------------------------------------------
# Arg parse
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --canonical)
            [[ $# -lt 2 ]] && { echo "ERROR: --canonical requires a path" >&2; exit 2; }
            CANONICAL="$2"; shift 2 ;;
        --vendored)
            [[ $# -lt 2 ]] && { echo "ERROR: --vendored requires a path" >&2; exit 2; }
            VENDORED="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^set -/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            echo "Usage: $(basename "$0") --vendored <path> [--canonical <path>]" >&2
            exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Prerequisite: jq
# ---------------------------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required but not found on PATH." >&2
    echo "  Install: brew install jq  (macOS)  |  apt-get install jq  (Debian/Ubuntu)" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------
if [[ -z "$VENDORED" ]]; then
    echo "ERROR: --vendored <path> is required (or set COCKPIT_VENDORED env var)." >&2
    echo "  Example: $(basename "$0") --vendored <opticon>/contract/schema/cockpit-contract.schema.json" >&2
    exit 2
fi

if [[ ! -f "$CANONICAL" ]]; then
    echo "ERROR: canonical schema not found: $CANONICAL" >&2
    echo "  Override with --canonical <path> or COCKPIT_CANONICAL env var." >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Extract versions
# ---------------------------------------------------------------------------
CANONICAL_VERSION="$(jq -r '.version // empty' "$CANONICAL")"
if [[ -z "$CANONICAL_VERSION" ]]; then
    echo "ERROR: could not read .version from canonical schema: $CANONICAL" >&2
    exit 2
fi

if [[ ! -f "$VENDORED" ]]; then
    echo "DRIFT: vendored schema not found at: $VENDORED" >&2
    echo "  Canonical version: v${CANONICAL_VERSION}" >&2
    echo "  Action: vendor schema/*.json from cockpit-contract/schema/ and run pnpm run contract:gen before ingest." >&2
    exit 1
fi

VENDORED_VERSION="$(jq -r '.version // empty' "$VENDORED")"
if [[ -z "$VENDORED_VERSION" ]]; then
    echo "DRIFT: could not read .version from vendored schema: $VENDORED" >&2
    echo "  Canonical version: v${CANONICAL_VERSION}" >&2
    echo "  Action: re-vendor schema/*.json and run pnpm run contract:gen before ingest." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------
if [[ "$CANONICAL_VERSION" == "$VENDORED_VERSION" ]]; then
    echo "in sync (v${CANONICAL_VERSION})"
    exit 0
else
    echo "DRIFT: canonical v${CANONICAL_VERSION} vs vendored v${VENDORED_VERSION} — re-vendor schema/*.json and run pnpm run contract:gen before ingest." >&2
    exit 1
fi
