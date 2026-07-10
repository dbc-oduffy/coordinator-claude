#!/usr/bin/env bash
# derive-session-hierarchy.sh — Derive the session/workstream hierarchy projection
#   from handoff frontmatter lineage and write a per-machine shard to disk.
#
# Purpose: Queries all handoffs (state/handoffs/ and archive/handoffs/) via
#   bin/query-records, extracts consumed_by fields (the derive-bridge: a consumed
#   handoff's consumed_by IS the harness session_id of the consuming session), and
#   builds a JSON array of session-hierarchy records keyed on session_id.
#   Resolves parent_session_id via a one-hop predecessor walk. Emits synthetic
#   workstream-type nodes grouping sessions by workstream slug (the translated
#   example-voice-system invariant: slug-grouping + branch-laterality + role-exclusivity).
#
#   Output path: state/session-hierarchy.<machine-slug>.json
#   Output shape: a JSON array of record objects (NOT a wrapper object).
#     C3 (query-session-hierarchy.sh) and C4 (bats tests) consume this via:
#       jq '.[] | select(...)' state/session-hierarchy.<slug>.json
#
#   Write discipline: full rebuild, atomic temp+rename (latest-wins). Per-machine
#   shard eliminates cross-machine git conflicts — each machine rebuilds its own
#   file independently; no merge conflict is possible.
#
#   Coverage honesty: the derive-bridge is consumed_by, present on only the
#   consumed-pickup minority of handoffs (~30% in practice). Unconsumed/handoff-
#   less sessions have no lineage-to-session_id bridge and are NOT emitted here;
#   they surface as the completeness:partial gap filled by ccos-4 journal and/or
#   ccos-2 agent_sessions enumeration. This is documented in the plan as the
#   explicit derive/author split: sessions without consumed_by = authored bucket.
#
# Spec backlink: docs/plans/2026-06-27-ccos-5-session-workstream-hierarchy-record.md § C2

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash >=4 guard (stock macOS /bin/bash is 3.2; brew bash is required)
# MUST be reachable before any bash-4 syntax (declare -A, mapfile, ${v^^} etc.)
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

# Source the state-root seam -- must precede coordinator_state_root calls (added by repoint-central-state-refs.sh C3)
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

# jq guard (house JSON tool — required for record construction)
if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq is required. Install via: brew install jq" >&2
  exit 1
fi

# Node guard (query-records.js requires node)
if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: node is required to run query-records.js" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Resolve coordinator root and repo root (cwd-scope guard)
# Script lives at: <root>/plugins/coordinator/bin/
# CLAUDE_HOME overrides; fall back to 4 levels up from SCRIPT_DIR.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CLAUDE_HOME:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"

# Sanity-check: the root must look like a ~/.claude repo (has plugins/).
# NOTE: state/ is NOT a marker post-stop-the-rot — central state migrated to example-orchestration-hub,
# so ~/.claude no longer has a state/ dir; plugins/ is the durable meta-repo marker.
if [[ ! -d "$ROOT/plugins" ]]; then
  echo "ERROR: resolved ROOT='$ROOT' does not look like a ~/.claude repo (missing plugins/)" >&2
  echo "  Set CLAUDE_HOME to the correct path or run from within the repo tree." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Machine slug (VERBATIM idiom — reused from append-goal-event.sh, coordinator
# standard: hostname → lowercase → all non-alnum runs → '-' → strip edges)
# ---------------------------------------------------------------------------
MACHINE_SLUG="$(hostname | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')"

# ---------------------------------------------------------------------------
# Output shard: per-machine, full-rebuild, atomic temp+rename
# ---------------------------------------------------------------------------
OUTPUT_FILE="$(coordinator_state_root --central)/session-hierarchy.${MACHINE_SLUG}.json"
TMP_FILE="${OUTPUT_FILE}.tmp.$$"

QUERY_RECORDS="${SCRIPT_DIR}/query-records.js"
if [[ ! -f "$QUERY_RECORDS" ]]; then
  echo "ERROR: query-records.js not found at $QUERY_RECORDS" >&2
  exit 1
fi

# Session ID for created_by_session (populated when CS_SESSION_ID is set in env)
CREATED_BY_SESSION="${CS_SESSION_ID:-}"

echo "[derive-session-hierarchy] ROOT=$ROOT" >&2
echo "[derive-session-hierarchy] Machine slug: $MACHINE_SLUG" >&2
echo "[derive-session-hierarchy] Output: $OUTPUT_FILE" >&2

# ---------------------------------------------------------------------------
# Collect handoff frontmatter via query-records (both active + archived)
# query-records outputs [{path, frontmatter}] JSON arrays.
# We do NOT re-parse handoff YAML here — that is the anti-scope.
# post-stop-the-rot: query-records appends state/handoffs/ under --root, and the
# meta-repo's handoffs now resolve to example-orchestration-hub — so the read root is example-orchestration-hub, NOT $ROOT
# (~/.claude, which no longer has state/handoffs/). $ROOT stays for the plugins/ guard.
# ---------------------------------------------------------------------------
QUERY_ROOT="$(coordinator_example_orchestration_hub_root)"
HANDOFFS_ACTIVE=$(node "$QUERY_RECORDS" --type handoff          --format json --root "$QUERY_ROOT" 2>/dev/null || echo '[]')
HANDOFFS_ARCHIVED=$(node "$QUERY_RECORDS" --type handoff-archived --format json --root "$QUERY_ROOT" 2>/dev/null || echo '[]')

# ---------------------------------------------------------------------------
# Build the hierarchy projection via jq.
#
# Derive-bridge logic (from the plan § "The handoff↔session map"):
#   session_id        ← handoff.consumed_by
#   workstream        ← handoff.workstream
#   branch            ← handoff.branch  [APPROXIMATION: stamped at handoff
#                       authoring time, i.e. the predecessor session's branch,
#                       NOT the consuming session's branch. Daily-branch-rename
#                       and cross-machine pickup can mis-attribute. Where ccos-4
#                       journal provides the consumer's actual branch, prefer
#                       that and fall back here. (Plan F3)]
#   parent_session_id ← predecessor-handoff's consumed_by (one-hop walk; null
#                       if predecessor is "none"/absent/unconsumed)
#   session_type      ← "blitz" when workstream slug contains blitz/mise-en-place
#                       (case-insensitive); else "session"
#
# Synthetic workstream nodes (one per distinct workstream slug):
#   session_type: "workstream", parent_session_id: null
#   (limb-2 invariant: workstream-type nodes carry no parent_session_id)
#
# Completeness honesty:
#   Records derived from a consumed handoff → completeness: complete
#   Unconsumed/handoff-less sessions have no consumed_by → NOT emitted here
#   (they fall to the authored/ccos-4 bucket, captured as completeness: partial
#   when filled by a future authored pass)
# ---------------------------------------------------------------------------
jq -n \
  --argjson active   "$HANDOFFS_ACTIVE" \
  --argjson archived "$HANDOFFS_ARCHIVED" \
  --arg     session  "$CREATED_BY_SESSION" \
  '
  # -----------------------------------------------------------------------
  # Combine both handoff sources
  # -----------------------------------------------------------------------
  ($active + $archived) as $all |

  # -----------------------------------------------------------------------
  # Build predecessor-basename → consumed_by lookup table.
  # The predecessor field stores a bare filename (e.g. "2026-06-23_foo.md");
  # handoff paths end with the same filename (last path component).
  # Index by basename so we can walk the predecessor chain in one hop.
  # -----------------------------------------------------------------------
  (
    $all
    | [.[] | {key: (.path | split("/") | last), value: (.frontmatter.consumed_by // null)}]
    | from_entries
  ) as $pred_lookup |

  # -----------------------------------------------------------------------
  # Restrict to handoffs that have consumed_by (the derive bridge)
  # -----------------------------------------------------------------------
  ($all | [.[] | select(.frontmatter.consumed_by != null)]) as $consumed |

  # -----------------------------------------------------------------------
  # Session records derived from consumed handoffs
  # -----------------------------------------------------------------------
  [
    $consumed[] |
    .path as $path |
    .frontmatter as $fm |

    # Base record fields (always present)
    {
      session_id:        $fm.consumed_by,
      session_type:      (
        if (($fm.workstream // "") | test("blitz|mise-en-place|bug-blitz"; "i"))
        then "blitz"
        else "session"
        end
      ),
      workstream:        ($fm.workstream // "unknown"),
      parent_session_id: (
        ($fm.predecessor // "none") as $pred |
        if ($pred == "none" or $pred == null or $pred == "")
        then null
        else ($pred_lookup[$pred] // null)
        end
      ),
      linked_handoffs:   [$path],
      system: {
        provenance_completeness: "complete",
        capture_source:          "derived_handoff_lineage",
        completeness:            "complete"
      }
    }
    # Conditionally add branch (type: string, not nullable — omit when absent)
    + if $fm.branch then {branch: $fm.branch} else {} end
    # Conditionally add created_by_session (omit when CS_SESSION_ID not set)
    + if ($session | length) > 0
      then {system: {
        provenance_completeness: "complete",
        capture_source:          "derived_handoff_lineage",
        completeness:            "complete",
        created_by_session:      $session
      }}
      else {}
      end
  ] as $session_records |

  # -----------------------------------------------------------------------
  # Synthetic workstream-type nodes — one per distinct workstream slug.
  # Limb-1: workstream identity is the slug, NOT any branch value.
  # Limb-2: workstream-type nodes carry no parent_session_id (null).
  # -----------------------------------------------------------------------
  ([$consumed[] | .frontmatter.workstream // "unknown"] | unique) as $workstreams |
  [
    $workstreams[] |
    {
      session_id:        ("workstream:" + .),
      session_type:      "workstream",
      workstream:        .,
      parent_session_id: null,
      linked_handoffs:   [],
      system:            {
        provenance_completeness: "complete",
        capture_source:          "derived_handoff_lineage",
        completeness:            "complete"
      }
    }
    + if ($session | length) > 0
      then {system: {
        provenance_completeness: "complete",
        capture_source:          "derived_handoff_lineage",
        completeness:            "complete",
        created_by_session:      $session
      }}
      else {}
      end
  ] as $workstream_nodes |

  # -----------------------------------------------------------------------
  # Emit: sessions first, synthetic workstream nodes appended
  # -----------------------------------------------------------------------
  $session_records + $workstream_nodes
  ' > "$TMP_FILE"

# Validate JSON before committing (belt-and-suspenders; jq -n should never
# produce invalid JSON, but verify before the atomic rename)
if ! jq empty "$TMP_FILE" 2>/dev/null; then
  echo "ERROR: jq produced invalid JSON in $TMP_FILE — aborting" >&2
  rm -f "$TMP_FILE"
  exit 1
fi

# Atomic rename (full rebuild, latest-wins; per-machine shard = no git conflicts)
mv "$TMP_FILE" "$OUTPUT_FILE"

# ---------------------------------------------------------------------------
# Emit stats to stderr (informational; not part of the output contract)
# ---------------------------------------------------------------------------
TOTAL=$(jq 'length' "$OUTPUT_FILE")
COMPLETE=$(jq '[.[] | select(.system.completeness == "complete")] | length' "$OUTPUT_FILE")
PARTIAL=$(jq '[.[] | select(.system.completeness == "partial")] | length' "$OUTPUT_FILE")
COUNT_SESSION=$(jq '[.[] | select(.session_type == "session")] | length' "$OUTPUT_FILE")
COUNT_BLITZ=$(jq '[.[] | select(.session_type == "blitz")] | length' "$OUTPUT_FILE")
COUNT_WS=$(jq '[.[] | select(.session_type == "workstream")] | length' "$OUTPUT_FILE")

echo "[derive-session-hierarchy] Done." >&2
echo "[derive-session-hierarchy]   Total records : $TOTAL" >&2
echo "[derive-session-hierarchy]   session       : $COUNT_SESSION" >&2
echo "[derive-session-hierarchy]   blitz         : $COUNT_BLITZ" >&2
echo "[derive-session-hierarchy]   workstream    : $COUNT_WS" >&2
echo "[derive-session-hierarchy]   complete      : $COMPLETE" >&2
echo "[derive-session-hierarchy]   partial       : $PARTIAL" >&2
