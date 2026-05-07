#!/usr/bin/env bash
# verify-parallel-review-lens-orthogonality.sh — Assert that the four reviewers named
# in the parallel-code-review skill's lens-domain manifest (a) have agent files on disk
# and (b) do not share any lens_domain value.
#
# Spec backlink: docs/plans/2026-05-06-parallel-code-review-weekly-gate.md Phase 3.5
#
# Purpose: Fail loudly at /update-docs Phase 11 time if a 5th reviewer is added with
# an overlapping lens domain, or if an agent file goes missing. The manifest is
# hardcoded in skills/parallel-code-review/SKILL.md — agent files are NOT the source
# of truth.
#
# Wire-in note: Wired into /update-docs Phase 11 (verify-sync phase) — see
# commands/update-docs.md. The /update-docs integration is a separate edit not
# done by this script.
#
# Exit 0: all agent files exist, no lens-domain collisions.
# Exit 1: one or more checks failed (diagnostic printed to stdout).
#
# Negative-spec: does NOT modify any files, does NOT dispatch agents, does NOT
# commit. Read-only assertion only.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve script location so paths work regardless of cwd
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILL_FILE="${COORDINATOR_DIR}/skills/parallel-code-review/SKILL.md"
AGENTS_DIR="${COORDINATOR_DIR}/agents"

# ---------------------------------------------------------------------------
# Verify the skill file itself exists before trying to parse it
# ---------------------------------------------------------------------------

if [[ ! -f "${SKILL_FILE}" ]]; then
  echo "ERROR: Skill file not found at expected path:"
  echo "  ${SKILL_FILE}"
  echo "Cannot verify lens-orthogonality without the manifest."
  exit 1
fi

# ---------------------------------------------------------------------------
# Parse the lens-domain manifest table from SKILL.md.
# The manifest lives between the "## Lens-Domain Manifest" heading and the
# next "---" horizontal rule or "##" heading. Rows have the format:
#   | <reviewer> | <lens_domain> | <rationale> |
# Skip the header row (contains "Reviewer") and separator rows ("---|").
# ---------------------------------------------------------------------------

PASS=1
declare -A SEEN_DOMAINS   # lens_domain → reviewer that claimed it first
REVIEWER_COUNT=0

# Extract only the lines belonging to the Lens-Domain Manifest section.
# Strategy: awk from the "## Lens-Domain Manifest" heading, stop at the
# next heading (##) or horizontal rule (^---).
manifest_lines=$(awk '
  /^## Lens-Domain Manifest/ { in_section=1; next }
  in_section && /^(##|---)/ { in_section=0 }
  in_section && /^\|/ { print }
' "${SKILL_FILE}")

while IFS='|' read -r _ reviewer lens_domain _ rest; do
  # Trim leading/trailing whitespace from each field
  reviewer="${reviewer#"${reviewer%%[![:space:]]*}"}"
  reviewer="${reviewer%"${reviewer##*[![:space:]]}"}"
  lens_domain="${lens_domain#"${lens_domain%%[![:space:]]*}"}"
  lens_domain="${lens_domain%"${lens_domain##*[![:space:]]}"}"

  # Skip header rows, separator rows, and empty parses
  [[ -z "${reviewer}" ]] && continue
  [[ "${reviewer}" == "Reviewer"* ]] && continue
  [[ "${reviewer}" == "---"* ]] && continue
  [[ "${lens_domain}" == "---"* ]] && continue
  [[ -z "${lens_domain}" ]] && continue

  REVIEWER_COUNT=$(( REVIEWER_COUNT + 1 ))

  # Extract the bare agent filename from the reviewer cell.
  # Cells look like: "the Staff Engineer (`agents/staff-eng.md`)"
  # or:              "security-audit-worker (`agents/security-audit-worker.md`)"
  agent_path=""
  if [[ "${reviewer}" =~ \`agents/([^\`]+)\` ]]; then
    agent_path="${AGENTS_DIR}/${BASH_REMATCH[1]}"
  fi

  # Assert agent file exists
  if [[ -n "${agent_path}" ]]; then
    if [[ ! -f "${agent_path}" ]]; then
      echo "FAIL: Agent file missing for reviewer '${reviewer}':"
      echo "  Expected: ${agent_path}"
      PASS=0
    fi
  else
    echo "WARN: Could not parse agent path from reviewer cell: '${reviewer}'"
  fi

  # Assert no two reviewers share a lens_domain
  if [[ -v "SEEN_DOMAINS[${lens_domain}]" ]]; then
    echo "FAIL: Lens-domain collision — '${lens_domain}' claimed by both:"
    echo "  '${SEEN_DOMAINS[${lens_domain}]}' and '${reviewer}'"
    PASS=0
  else
    SEEN_DOMAINS["${lens_domain}"]="${reviewer}"
  fi

done <<< "${manifest_lines}"

# ---------------------------------------------------------------------------
# Sanity check: we should have found at least the 4 canonical reviewers
# ---------------------------------------------------------------------------

if (( REVIEWER_COUNT < 4 )); then
  echo "FAIL: Expected at least 4 reviewer rows in the manifest table, found ${REVIEWER_COUNT}."
  echo "  Check that the lens-domain manifest table in SKILL.md is intact."
  PASS=0
fi

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

if (( PASS == 1 )); then
  echo "OK: ${REVIEWER_COUNT} reviewers — agent files exist, no lens-domain collisions."
  exit 0
else
  echo ""
  echo "Lens-orthogonality check failed. Fix the issues above before proceeding."
  echo "Manifest source: ${SKILL_FILE}"
  exit 1
fi
