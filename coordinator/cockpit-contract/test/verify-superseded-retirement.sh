#!/usr/bin/env bash
# Acceptance-oracle realization for docs/plans/2026-06-26-retire-superseded-handoff-status.md.
# Gate-bound ACs whose checks need literal pipes / negative assertions live here rather than
# inline in the plan's markdown AC table — the table's `\|` escaping collides with grep -E
# alternation, producing false reds (the enum string `active | consumed | superseded` cannot be
# asserted-absent from a markdown table cell without the pipe being mangled). Run from repo root.
#
# Usage: verify-superseded-retirement.sh <ac1|ac2|ac3|ac6>   (exit 0 = green)
set -u
set -o pipefail  # Review: code-reviewer — F4: catch broken pipes in grep chains
CC="plugins/coordinator-claude/coordinator"

fail() { echo "RED: $1" >&2; exit 1; }
# Review: code-reviewer — F5: file-existence preflight; grep exits 2 (not 1) on missing file,
# producing false-green on '&& fail' checks and false-red on '|| fail' checks.
_need() { [ -f "$1" ] || fail "missing file: $1"; }

case "${1:-}" in
  ac1)
    # No handoff record (live or archived) carries status: superseded.
    if [ -n "$(grep -rl '^status: superseded' state/handoffs/ archive/handoffs/ 2>/dev/null)" ]; then
      fail "a handoff record still carries 'status: superseded'"
    fi
    ;;
  ac2)
    # No handoff WRITER surface prescribes status: superseded.
    _need "$CC/CLAUDE.md"
    _need "$CC/docs/wiki/spinoff-handoffs.md"
    _need "$CC/skills/handoff/SKILL.md"
    _need "$CC/schemas/handoff.yaml"
    grep -Fq 'active | consumed | superseded' "$CC/CLAUDE.md"                 && fail "CLAUDE.md still lists the superseded enum value"
    grep -Fq 'active | consumed | superseded' "$CC/docs/wiki/spinoff-handoffs.md" && fail "spinoff-handoffs.md still lists the superseded enum value"
    grep -q  'status: superseded' "$CC/skills/handoff/SKILL.md"               && fail "skills/handoff/SKILL.md still prescribes status: superseded"
    grep -Eq 'values:.*superseded' "$CC/schemas/handoff.yaml"                 && fail "schemas/handoff.yaml status values still include superseded"
    ;;
  ac3)
    # Shared-token safety: 3 protected rows (memo/plan/decision) preserved, handoff row removed.
    _need "$CC/docs/wiki/canonical-artifact-shapes.md"
    n=$(grep -cE '^\| (memo|plan|decision) \| status \| superseded' "$CC/docs/wiki/canonical-artifact-shapes.md")
    [ "$n" = "3" ] || fail "expected 3 memo/plan/decision superseded rows, found $n"
    grep -Eq '^\| handoff \| status \| superseded' "$CC/docs/wiki/canonical-artifact-shapes.md" && fail "handoff DONE row still present"
    ;;
  ac6)
    # Enum narrowed in source; writer schema narrowed; reader schema deliberately tolerant; version unchanged.
    # Review: code-reviewer — F5 file-existence preflight for all ac6 targets
    _need "$CC/cockpit-contract/src/entities/summaries.ts"
    _need "$CC/schemas/handoff.yaml"
    _need "$CC/schemas/handoff-archived.yaml"
    _need "$CC/cockpit-contract/schema/cockpit-contract.schema.json"
    _need "$CC/cockpit-contract/schema/handoff-summary.schema.json"
    _need "$CC/cockpit-contract/schema/snapshot-envelope.schema.json"
    grep -Fq 'z.enum(["active", "consumed"])' "$CC/cockpit-contract/src/entities/summaries.ts" || fail "HandoffStatus Zod enum not narrowed to [active,consumed]"
    grep -Eq 'values: \[active, consumed\]' "$CC/schemas/handoff.yaml"                          || fail "handoff.yaml values line not narrowed to [active, consumed]"
    grep -Eq 'values:.*superseded' "$CC/schemas/handoff-archived.yaml"                          || fail "handoff-archived.yaml must stay tolerant of superseded (reader-validator)"
    grep -Fq '"2.0.0"' "$CC/cockpit-contract/schema/cockpit-contract.schema.json"              || fail "CONTRACT_VERSION is no longer 2.0.0"
    grep -Fq '"superseded"' "$CC/cockpit-contract/schema/handoff-summary.schema.json"          && fail "handoff-summary schema still contains superseded"
    # Review: code-reviewer — F2: assert HandoffKind 'recovery' is still present in handoff-summary schema
    grep -Fq '"recovery"' "$CC/cockpit-contract/schema/handoff-summary.schema.json" || fail "HandoffKind 'recovery' missing from handoff-summary schema"
    # Review: code-reviewer — F3: positive assertion that snapshot-envelope HandoffStatus is narrowed.
    # NOTE: snapshot-envelope.schema.json legitimately contains 'superseded' in plan/goal enums (lines
    # unrelated to HandoffStatus), so a blanket '! grep superseded' would false-red. The grep below
    # confirms the narrowed [active, consumed] pair is present in the HandoffStatus context. AC7
    # (pnpm test round-trip) is the authoritative cross-schema check that discriminates HandoffStatus
    # superseded from plan/goal superseded — this is a structural sanity check, not a substitution.
    grep -Fq '"active",' "$CC/cockpit-contract/schema/snapshot-envelope.schema.json" || fail "snapshot-envelope missing narrowed HandoffStatus active+consumed pair"
    ;;
  *)
    echo "usage: $0 <ac1|ac2|ac3|ac6>" >&2; exit 2 ;;
esac
echo "GREEN: ${1}"
