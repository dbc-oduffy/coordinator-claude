#!/usr/bin/env bash
# verify-parallel-review-lens-orthogonality.sh — Assert the parallel-code-review gate's
# two structural properties:
#   (1) STATIC (no args): the orthogonal lens domains in the skill's lens-domain manifest
#       (3 specialist workers + code-semantics-as-a-class) (a) have agent files on disk
#       and (b) do not share any lens_domain value.
#   (2) RUNTIME (--chunk-manifest <tsv>): the N code-semantics chunk partitions are
#       disjoint by file-scope — no file appears in two chunks. Runs the static check
#       first, then the chunk-disjointness check.
#
# Spec backlink: docs/plans/2026-05-06-parallel-code-review-weekly-gate.md Phase 3.5
# Spec backlink: docs/plans/2026-05-23-weekly-gate-restructure-and-arch-survey-audit-rename.md § Strand 1c
#
# Purpose: Fail loudly at /update-docs Phase 11 time if a 5th orthogonal lens is added
# with an overlapping lens domain, or if an agent file goes missing; and fail loudly at
# pre-dispatch time if the chunk partitioning is not disjoint by file-scope (which would
# break the synthesizer's convergence logic). The manifest is hardcoded in
# skills/parallel-code-review/SKILL.md — agent files are NOT the source of truth.
#
# Wire-in note: the no-arg form is wired into /update-docs Phase 11 (verify-sync phase);
# the --chunk-manifest form is called by skills/parallel-code-review/SKILL.md at
# pre-dispatch time.
#
# Chunk-manifest format (TSV, one file per line): "chunk-<k>\t<relpath>".
#
# Exit 0: all checks passed.
# Exit 1: one or more checks failed (diagnostic printed to stdout).
#
# Negative-spec: does NOT modify any files, does NOT dispatch agents, does NOT
# commit. Read-only assertion only.

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing: optional --chunk-manifest <path>
# ---------------------------------------------------------------------------

CHUNK_MANIFEST=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --chunk-manifest)
      CHUNK_MANIFEST="${2:-}"
      if [[ -z "${CHUNK_MANIFEST}" ]]; then
        echo "ERROR: --chunk-manifest requires a path argument." >&2
        exit 1
      fi
      shift 2
      ;;
    *)
      echo "ERROR: unknown argument '$1' (usage: $0 [--chunk-manifest <tsv-path>])" >&2
      exit 1
      ;;
  esac
done

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
  [[ "${reviewer}" == "Lens"* ]] && continue   # header: "Lens (agent)"
  [[ "${reviewer}" == "---"* ]] && continue
  [[ "${lens_domain}" == "---"* ]] && continue
  [[ "${lens_domain}" == "Lens domain"* ]] && continue
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
    # The manifest is machine-authored; every lens row must carry a backtick-delimited
    # `agents/<file>.md` path. A row that reaches here (after header/separator skips) with
    # no parseable path is a malformed manifest — FAIL, do not silently pass.
    echo "FAIL: Could not parse agent path from reviewer cell: '${reviewer}'"
    PASS=0
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
# Sanity check: we should have found at least the 4 canonical orthogonal lenses
# (code-semantics-as-a-class + security + deps + tests)
# ---------------------------------------------------------------------------

if (( REVIEWER_COUNT < 4 )); then
  echo "FAIL: Expected at least 4 orthogonal-lens rows in the manifest table, found ${REVIEWER_COUNT}."
  echo "  Check that the lens-domain manifest table in SKILL.md is intact."
  PASS=0
fi

# ---------------------------------------------------------------------------
# Static result
# ---------------------------------------------------------------------------

if (( PASS == 1 )); then
  echo "OK (static): ${REVIEWER_COUNT} orthogonal lenses — agent files exist, no lens-domain collisions."
else
  echo ""
  echo "Lens-orthogonality (static) check failed. Fix the issues above before proceeding."
  echo "Manifest source: ${SKILL_FILE}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Chunk-disjointness check (only when --chunk-manifest was provided)
# ---------------------------------------------------------------------------

if [[ -z "${CHUNK_MANIFEST}" ]]; then
  exit 0
fi

if [[ ! -f "${CHUNK_MANIFEST}" ]]; then
  echo "FAIL: chunk manifest not found at: ${CHUNK_MANIFEST}"
  exit 1
fi

CHUNK_PASS=1
declare -A FILE_OWNER   # relpath → first chunk that claimed it
CHUNK_FILE_COUNT=0
declare -A CHUNKS_SEEN  # chunk-id → 1

# Parse TSV: "chunk-<k><TAB><relpath>". Tolerate blank lines and leading/trailing
# whitespace. A file claimed by two distinct chunk ids is a disjointness violation.
while IFS=$'\t' read -r chunk_id relpath _rest; do
  # Trim whitespace
  chunk_id="${chunk_id#"${chunk_id%%[![:space:]]*}"}"
  chunk_id="${chunk_id%"${chunk_id##*[![:space:]]}"}"
  relpath="${relpath#"${relpath%%[![:space:]]*}"}"
  relpath="${relpath%"${relpath##*[![:space:]]}"}"

  [[ -z "${chunk_id}" ]] && continue
  [[ -z "${relpath}" ]] && continue
  [[ "${chunk_id}" == \#* ]] && continue   # allow comment lines

  CHUNKS_SEEN["${chunk_id}"]=1
  CHUNK_FILE_COUNT=$(( CHUNK_FILE_COUNT + 1 ))

  if [[ -v "FILE_OWNER[${relpath}]" ]]; then
    if [[ "${FILE_OWNER[${relpath}]}" != "${chunk_id}" ]]; then
      echo "FAIL: chunk partitions not disjoint — '${relpath}' claimed by both:"
      echo "  '${FILE_OWNER[${relpath}]}' and '${chunk_id}'"
      CHUNK_PASS=0
    fi
    # Same file listed twice under the same chunk is harmless; ignore.
  else
    FILE_OWNER["${relpath}"]="${chunk_id}"
  fi
done < "${CHUNK_MANIFEST}"

if (( CHUNK_FILE_COUNT == 0 )); then
  echo "FAIL: chunk manifest '${CHUNK_MANIFEST}' contained no chunk/file rows."
  echo "  Expected lines of the form 'chunk-<k><TAB><relpath>'."
  exit 1
fi

if (( CHUNK_PASS == 1 )); then
  echo "OK (chunks): ${#CHUNKS_SEEN[@]} chunks over ${#FILE_OWNER[@]} distinct files — partitions disjoint by file-scope."
  exit 0
else
  echo ""
  echo "Chunk-disjointness check failed. Re-chunk so no file appears in two chunks."
  echo "Chunk manifest: ${CHUNK_MANIFEST}"
  exit 1
fi
