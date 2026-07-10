#!/usr/bin/env bash
# audit-roadmap.sh — Phase 2 close cross-file audits for coordinator:roadmap-planning.
#
# Closes the gap that bin/lint-frontmatter.js cannot enforce per-file: rules that compare
# multiple stubs in the active set, or cross-reference a stub against state/roadmap/<run-id>/pm-gates.md.
#
# Spec backlink: docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md § Phase 5
# the Staff Engineer review finding: P1-1 (audit script must ship in v1, not be deferred to post-dogfood).
#
# Usage: audit-roadmap.sh <run-id> [--root <dir>]
#
# Exits 0 on pass; 1 on any audit failure with diagnostic output.

set -euo pipefail

RUN_ID="${1:-}"
if [ -z "$RUN_ID" ]; then
  echo "Usage: $0 <run-id> [--root <dir>]" >&2
  echo "  Audits the roadmap with roadmap_id=<run-id> for Phase 2 close gates." >&2
  exit 2
fi
# Review: code-reviewer (F4/P2) — allowlist slug guard; a bare emptiness check leaves
# query-corruption surface open (AND-injection, YAML metacharacters). Detect-then-fail-loud.
if ! printf '%s' "$RUN_ID" | grep -qE '^[a-z0-9][a-z0-9-]*$'; then
  echo "ERROR: <run-id> must match ^[a-z0-9][a-z0-9-]*\$ (got: \"${RUN_ID}\")" >&2
  exit 2
fi
shift  # consume RUN_ID; remaining flags parsed below after lib sources

# Source the state-root seam -- must precede coordinator_state_root calls (added by repoint-central-state-refs.sh C3)
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"
# shellcheck source=../lib/records-query-facade.sh
source "${_CSR_LIB_DIR}/records-query-facade.sh"

# CODE root — self-relative to this script; where schema.js / roadmap-graph.js live.
# Hard exit if missing: these libs are load-bearing for every node -e block below.
_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)"
if [[ ! -d "$_LIB_DIR" ]] || [[ ! -f "$_LIB_DIR/schema.js" ]]; then
  echo "ERROR: audit-roadmap.sh: lib/schema.js not found at ${_LIB_DIR}/schema.js — coordinator install may be incomplete" >&2
  exit 1
fi

# DATA root — where roadmap stubs live. Default: the repo that owns the roadmap
# being audited (cwd/consumer repo), derived from coordinator_state_root's Rule 5
# resolution ($GIT_ROOT/state for a sibling repo; example-orchestration-hub state for the meta-repo)
# with the trailing /state segment stripped back to the repo root that
# cc_records_query / query-records.js --root expects (it globs state/handoffs/*.md
# relative to this root). This is the same seam PMG/RECON already read
# reconciliation.md and pm-gates.md from — Audit 1 previously compared
# verdicts-from-the-consumer-repo against stubs-from-example-orchestration-hub, always finding 0
# stubs on a consumer repo (silent 0==0 dead-gate). Precedence: --root flag >
# cwd-repo default. There is deliberately NO $EXAMPLE_ORCHESTRATION_HUB_ROOT env-var precedence
# branch here: an ambient/leaked EXAMPLE_ORCHESTRATION_HUB_ROOT from an unrelated caller or parent
# shell (e.g. a wrapping /workday-start step, or a var left exported by a prior
# cc_records_query call in the same shell) would otherwise silently re-root this
# audit back to example-orchestration-hub on a consumer/sibling repo — precisely the dead-gate class
# this script exists to fix, just triggered by env leakage instead of a code bug.
# Callers that need to force a specific root (integration tests, State-3
# transport-failure fixtures, explicit cross-repo audits) MUST use --root <dir>,
# which is unambiguous opt-in and cannot be triggered by an inherited env var.
# Review: code-reviewer (F2/P2) — dropped the EXAMPLE_ORCHESTRATION_HUB_ROOT env-precedence branch;
# the previous "honor caller-preset EXAMPLE_ORCHESTRATION_HUB_ROOT" framing was itself an
# unguarded re-introduction surface for the same dead-gate bug.
# RUN_ID was consumed via shift above; parse remaining flags now that libs are sourced.
DATA_ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      if [[ -z "${2:-}" ]]; then
        echo "ERROR: --root requires a directory argument" >&2
        exit 2
      fi
      DATA_ROOT="$2"
      shift 2
      ;;
    *)
      echo "ERROR: unexpected argument: $1" >&2
      exit 2
      ;;
  esac
done
if [[ -z "$DATA_ROOT" ]]; then
  DATA_ROOT="$(dirname "$(coordinator_state_root)")"
fi
# Thread DATA_ROOT to the facade layer: cc_records_query honors $EXAMPLE_ORCHESTRATION_HUB_ROOT when set.
export EXAMPLE_ORCHESTRATION_HUB_ROOT="$DATA_ROOT"

PMG="$(coordinator_state_root)/roadmap/${RUN_ID}/pm-gates.md"
RECON="$(coordinator_state_root)/roadmap/${RUN_ID}/reconciliation.md"

# QR is only used in State-1 (seam absent → legacy node fallback). Resolve self-relative
# first (authoring-repo layout); fall back to .doe-root/CLAUDE_PLUGIN_ROOT consumer layout.
# No hard-exit on missing QR — State-1 failure is caught loudly at cc_records_query call sites.
QR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/query-records.js"
if [[ ! -f "$QR" ]]; then
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  if [[ -n "$_doe_root" ]] && [[ -d "${_doe_root}/coordinator" ]]; then
    QR="${CLAUDE_PLUGIN_ROOT:-${_doe_root}/coordinator}/bin/query-records.js"
    # shellcheck source=../lib/coordinator-trusted-root-guard.sh
    source "${_CSR_LIB_DIR}/coordinator-trusted-root-guard.sh"
    coordinator_trusted_root_guard --mode=fail-loud --root="$QR" --site="$0"
  fi
fi

EXIT_CODE=0
fail() { echo "FAIL: $*" >&2; EXIT_CODE=1; }
pass() { echo "PASS: $*"; }

# Abort immediately on a State-3 hard error from cc_records_query (seam present but
# transport broken). State-3 with the old || true pattern would yield empty results,
# silently skipping audits 2, 3, and 5 — a dead-gate false pass. Abort instead.
_abort_on_state3() {
  local _rc="$1" _context="$2"
  if [[ "$_rc" -ne 0 ]]; then
    printf 'FAIL: records.query State-3 hard error (rc=%d) in %s — native engine present-but-broken; aborting to avoid dead-gate silent skip\n' \
      "$_rc" "$_context" >&2
    exit 3
  fi
}

# --- Audit 1: stub-coverage (brief recommendation G) ----------------------
# Verdict-to-stub coverage: count of MERGE+KEEP verdicts in reconciliation.md
# must equal count of stubs on disk with this roadmap_id.

if [ ! -f "$RECON" ]; then
  fail "reconciliation.md not found at $RECON — Phase 1 incomplete"
else
  # Count verdicts. Primary format: markdown table rows with **KEEP** / **MERGE**
  # starting the 2nd OR 3rd pipe-delimited cell. The roadmap-planning skill's
  # reconciliation examples (and observed roadmap authoring, e.g. example-cockpit-repo
  # cockpit-tactical-2026-07-07) put the verdict token in the 2nd cell
  # (`| cluster | **KEEP** | notes |`); a 3rd-cell-only regex silently matched 0
  # rows against that shape, contributing to a 0==0 dead-gate false PASS.
  # `^\|[^|]*\|\s*\*\*KEEP\*\*` anchors to the 2nd cell; the alternate
  # `^\|[^|]*\|[^|]*\|\s*\*\*KEEP\*\*` anchors to the 3rd cell (older
  # `| # | cluster | verdict |` layout, still supported). Anchoring to a cell
  # START (not free match anywhere in the line) avoids matching KEEP/MERGE
  # tokens in free-text Note columns (e.g. "(MERGE-into-4)" in a note cell must
  # not count as a MERGE verdict). Known residual surface: a `| # | notes | verdict |`
  # 3-column layout where the 2nd cell is itself free text starting with
  # **KEEP**/**MERGE** (not the verdict column) WOULD double-count under the
  # 2nd-cell alternative — regression-tested (not double-counted today) in
  # test-audit-roadmap-verdict-regex.sh; the roadmap-planning skill's actual table
  # shapes never put verdict-prefixed free text ahead of the real verdict cell.
  # Review: code-reviewer (F3/P2) — added the regression fixture; comment now
  # names the residual surface explicitly rather than leaving it implicit.
  # Cell values like "**KEEP** (cross-repo relay)"
  # are correctly matched — only the cell START is required to be **KEEP** /
  # **MERGE**, not the entire cell.
  # Back-compat: if the table form matches 0 rows, fall back to prose "Verdict: KEEP".
  KEEP_COUNT=$(grep -cE "^\|[^|]*\|\s*\*\*KEEP\*\*|^\|[^|]*\|[^|]*\|\s*\*\*KEEP\*\*" "$RECON" || true)
  # Review: code-reviewer (F4) — if table-form has genuinely zero KEEP verdicts, prose fallback also returns 0 — correct in both cases.
  if [ "$KEEP_COUNT" -eq 0 ]; then
    KEEP_COUNT=$(grep -ciE "verdict:\s*keep\b" "$RECON" || true)
  fi
  MERGE_COUNT=$(grep -cE "^\|[^|]*\|\s*\*\*MERGE\*\*|^\|[^|]*\|[^|]*\|\s*\*\*MERGE\*\*" "$RECON" || true)
  if [ "$MERGE_COUNT" -eq 0 ]; then
    MERGE_COUNT=$(grep -ciE "verdict:\s*merge\b" "$RECON" || true)
  fi
  EXPECTED=$((KEEP_COUNT + MERGE_COUNT))

  # Count stubs across both live (state/handoffs/) and archived (archive/handoffs/).
  # Counting only live stubs false-fails for partially-shipped roadmaps where stubs have
  # been consumed and moved to archive.
  _rq_rc=0
  _rq_live_paths=$(cc_records_query handoff \
    "kind=spinoff-roadmap AND roadmap_id=${RUN_ID}" paths) || _rq_rc=$?
  _abort_on_state3 "$_rq_rc" "Audit 1 LIVE_COUNT"
  LIVE_COUNT=$(printf '%s\n' "$_rq_live_paths" | grep -c . || true)
  _rq_rc=0
  _rq_arch_paths=$(cc_records_query handoff-archived \
    "kind=spinoff-roadmap AND roadmap_id=${RUN_ID}" paths) || _rq_rc=$?
  _abort_on_state3 "$_rq_rc" "Audit 1 ARCH_COUNT"
  ARCH_COUNT=$(printf '%s\n' "$_rq_arch_paths" | grep -c . || true)
  STUB_COUNT=$(( LIVE_COUNT + ARCH_COUNT ))

  if [ "$STUB_COUNT" -eq 0 ] && [ "$EXPECTED" -eq 0 ]; then
    # Defense-in-depth: a real roadmap never legitimately has both a 0 stub
    # count AND 0 KEEP/MERGE verdicts at Phase 2 close — that combination is
    # the silent dead-gate signature (e.g. a mis-rooted DATA_ROOT querying an
    # empty tree while reconciliation.md's verdict format also fails to parse).
    # Fail loud instead of letting 0==0 pass as coverage.
    fail "Stub-coverage: 0 stubs on disk AND 0 KEEP/MERGE verdicts parsed from $RECON — this is the dead-gate signature (a real roadmap never legitimately has both sides zero at Phase 2 close). Check DATA_ROOT rooting and the reconciliation.md verdict table format."
  elif [ "$STUB_COUNT" -ne "$EXPECTED" ]; then
    fail "Stub-coverage mismatch: ${STUB_COUNT} stubs on disk (${LIVE_COUNT} live + ${ARCH_COUNT} archived), ${EXPECTED} expected (KEEP=${KEEP_COUNT} + MERGE=${MERGE_COUNT}). See $RECON."
  else
    pass "Stub-coverage: ${STUB_COUNT} stubs (${LIVE_COUNT} live + ${ARCH_COUNT} archived) match ${EXPECTED} verdicts (KEEP=${KEEP_COUNT}, MERGE=${MERGE_COUNT})."
  fi
fi

# --- Audit 2: at most one ready_to_fire per (roadmap_id, sprint, wave) ----
# Validator pass per skill Step 2.7. Implements the rule across the active stub set.
# Wave is sprint-LOCAL (SKILL.md § "Wave = single-dispatch parallel fan-out within a
# sprint"), so the uniqueness key is (sprint, wave), not wave alone — otherwise wave 1
# of sprint 1 falsely collides with wave 1 of sprint 4.

_rq_rc=0
READY_PATHS=$(cc_records_query handoff \
  "kind=spinoff-roadmap AND roadmap_id=${RUN_ID} AND deployment_state=ready_to_fire" \
  paths) || _rq_rc=$?
_abort_on_state3 "$_rq_rc" "Audit 2 READY_PATHS"

if [ -n "$READY_PATHS" ]; then
  # Extract sprint:wave composite per file via frontmatter parse. Use node one-liner to keep schema-aware.
  # argv[1]=_LIB_DIR (require path), argv[2]=DATA_ROOT (stub file-read root), argv[3]=stub path (relative to DATA_ROOT)
  SLOTS=$(echo "$READY_PATHS" | while IFS= read -r p; do
    [ -z "$p" ] && continue
    node -e "// verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
      const fs=require('fs');
      const path=require('path');
      const {parseFrontmatter} = require(path.join(process.argv[1], 'schema.js'));
      const c = fs.readFileSync(path.join(process.argv[2], process.argv[3]),'utf8');
      const fm = parseFrontmatter(c).frontmatter || {};
      const s = (fm.sprint === undefined || fm.sprint === null) ? 'NO_SPRINT' : fm.sprint;
      const w = (fm.wave === undefined || fm.wave === null) ? 'NO_WAVE' : fm.wave;
      console.log('s' + s + ':w' + w);
    " -- "$_LIB_DIR" "$DATA_ROOT" "$p" 2>/dev/null || echo "PARSE_ERROR"
  done)

  # Review: code-reviewer (F1/P1) — PARSE_ERROR sentinel from a failed node frontmatter parse
  # would appear as a duplicate slot if two stubs both fail to parse, yielding a misleading gate
  # block. Detect parse failures first, fail with a clear message, then strip before dup-check.
  PARSE_ERRORS=$(echo "$SLOTS" | grep -c '^PARSE_ERROR$' || true)
  if [ "$PARSE_ERRORS" -gt 0 ]; then
    fail "Audit 2: ${PARSE_ERRORS} ready_to_fire stub(s) could not have their (sprint, wave) slot parsed — check schema.js path and stub YAML frontmatter"
  fi
  SLOTS_CLEAN=$(echo "$SLOTS" | grep -v '^PARSE_ERROR$' || true)
  DUPES=$(echo "$SLOTS_CLEAN" | sort | uniq -d)
  if [ -n "$DUPES" ]; then
    fail "Multiple ready_to_fire stubs in the same (roadmap_id, sprint, wave): slots [${DUPES}]. At most one ready_to_fire per (sprint, wave) allowed."
  else
    READY_COUNT=$(echo "$READY_PATHS" | grep -c .)
    pass "ready_to_fire uniqueness: ${READY_COUNT} ready stubs across distinct (sprint, wave) slots."
  fi
fi

# --- Audit 3: pm-gates.md cross-reference (brief recommendation E) -------
# Every stub with gate_dependency starting "PM " MUST have a matching stub_id row in pm-gates.md.
# Every pending row in pm-gates.md MUST be referenced by at least one stub.

_rq_rc=0
PM_STUBS=$(cc_records_query handoff \
  "kind=spinoff-roadmap AND roadmap_id=${RUN_ID} AND deployment_state=awaiting_gate" \
  paths) || _rq_rc=$?
_abort_on_state3 "$_rq_rc" "Audit 3 PM_STUBS"

PM_STUB_IDS=""
if [ -n "$PM_STUBS" ]; then
  while IFS= read -r p; do
    [ -z "$p" ] && continue
    # argv[1]=_LIB_DIR (require path), argv[2]=DATA_ROOT (stub file-read root), argv[3]=stub path
    TC=$(node -e "// verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
      const fs=require('fs');
      const path=require('path');
      const {parseFrontmatter} = require(path.join(process.argv[1], 'schema.js'));
      const c = fs.readFileSync(path.join(process.argv[2], process.argv[3]),'utf8');
      const fm = parseFrontmatter(c).frontmatter || {};
      const gd = String(fm.gate_dependency || '');
      if (gd.startsWith('PM ')) console.log(fm.stub_id || '');
    " -- "$_LIB_DIR" "$DATA_ROOT" "$p" 2>/dev/null || echo "")
    [ -n "$TC" ] && PM_STUB_IDS="${PM_STUB_IDS} ${TC}"
  done <<< "$PM_STUBS"
fi

if [ -n "${PM_STUB_IDS// /}" ]; then
  if [ ! -f "$PMG" ]; then
    fail "pm-gates.md missing at $PMG — found PM-prefixed gate_dependency on stub_ids: ${PM_STUB_IDS}"
  else
    PMG_CONTENT=$(cat "$PMG")
    for stub in $PM_STUB_IDS; do
      if ! echo "$PMG_CONTENT" | grep -qF "$stub"; then
        fail "Stub ${stub} has gate_dependency starting 'PM ' but is not cross-referenced in pm-gates.md"
      fi
    done
    [ "$EXIT_CODE" -eq 0 ] && pass "pm-gates.md cross-references: all ${PM_STUB_IDS} present."
  fi
fi

# --- Audit 4: pending pm-gates rows reference at least one stub ----------
# Inverse of Audit 3: every "pending" row in pm-gates.md must name a stub_id that exists.

if [ -f "$PMG" ]; then
  PENDING_STUBS=$(awk -F'|' '/pending/ { gsub(/[ \t]+/,"",$3); if ($3 ~ /^[a-z]+-[0-9]+$/) print $3 }' "$PMG" 2>/dev/null || true)
  if [ -n "$PENDING_STUBS" ]; then
    # Review: code-reviewer (F2) — union live + archived handoffs so an archived stub doesn't false-fail Audit 4 (mirrors Audit 1).
    _rq_rc=0
    _rq_json_live=$(cc_records_query handoff \
      "kind=spinoff-roadmap AND roadmap_id=${RUN_ID}" json) || _rq_rc=$?
    _abort_on_state3 "$_rq_rc" "Audit 4 ALL_STUBS_LIVE"
    ALL_STUBS_LIVE=$(printf '%s\n' "$_rq_json_live" \
      | node -e "let d=''; process.stdin.on('data',c=>d+=c).on('end',()=>{const a=JSON.parse(d); a.forEach(r=>console.log(r.frontmatter.stub_id||''))})" 2>/dev/null || true) # verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
    _rq_rc=0
    _rq_json_arch=$(cc_records_query handoff-archived \
      "kind=spinoff-roadmap AND roadmap_id=${RUN_ID}" json) || _rq_rc=$?
    _abort_on_state3 "$_rq_rc" "Audit 4 ALL_STUBS_ARCH"
    ALL_STUBS_ARCH=$(printf '%s\n' "$_rq_json_arch" \
      | node -e "let d=''; process.stdin.on('data',c=>d+=c).on('end',()=>{const a=JSON.parse(d); a.forEach(r=>console.log(r.frontmatter.stub_id||''))})" 2>/dev/null || true) # verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
    ALL_STUBS=$(printf '%s\n%s' "$ALL_STUBS_LIVE" "$ALL_STUBS_ARCH" | grep -v '^[[:space:]]*$' || true)
    for stub in $PENDING_STUBS; do
      if ! echo "$ALL_STUBS" | grep -qFx "$stub"; then
        fail "pm-gates.md has pending row for ${stub} but no stub with that stub_id exists in roadmap_id=${RUN_ID}"
      fi
    done
  fi
fi

# --- Audit 5: dependency-order invariant ----------------------------------
# For every edge A blocked_by B (B ships first), verify:
#   number(B) < number(A)                             [strict]
#   (sprint(B), wave(B)) <_lex (sprint(A), wave(A))  [strict; equal slot is a violation]
# Missing sprint on either endpoint fails loud. Edges to absent stub_ids are
# unresolved (not silently dropped). Cycles fail loud.
# Mirrors Audit 1 in enumerating live + archived stubs so partially-shipped
# roadmaps don't false-fail.

_rq_rc=0
A5_LIVE_PATHS=$(cc_records_query handoff \
  "kind=spinoff-roadmap AND roadmap_id=${RUN_ID}" paths) || _rq_rc=$?
_abort_on_state3 "$_rq_rc" "Audit 5 A5_LIVE_PATHS"
_rq_rc=0
A5_ARCH_PATHS=$(cc_records_query handoff-archived \
  "kind=spinoff-roadmap AND roadmap_id=${RUN_ID}" paths) || _rq_rc=$?
_abort_on_state3 "$_rq_rc" "Audit 5 A5_ARCH_PATHS"
A5_ALL_PATHS=$(printf '%s\n%s' "$A5_LIVE_PATHS" "$A5_ARCH_PATHS" | grep -v '^[[:space:]]*$' || true)

if [ -z "$A5_ALL_PATHS" ]; then
  pass "Audit 5: no spinoff-roadmap stubs found for roadmap_id=${RUN_ID} — dependency-order check skipped."
else
  # Build a JSON array of stub descriptors by parsing each file's frontmatter.
  # Fields extracted: stub_id, sprint, wave, blocked_by (array).
  # argv[1]=_LIB_DIR (require path), argv[2]=DATA_ROOT (stub file-read root), argv[3]=stub path
  A5_STUBS_JSON=$(echo "$A5_ALL_PATHS" | while IFS= read -r p; do
    [ -z "$p" ] && continue
    node -e "// verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
      const fs=require('fs');
      const path=require('path');
      const {parseFrontmatter} = require(path.join(process.argv[1], 'schema.js'));
      const c = fs.readFileSync(path.join(process.argv[2], process.argv[3]),'utf8');
      const fm = parseFrontmatter(c).frontmatter || {};
      const entry = {
        stub_id: fm.stub_id || null,
        // Review: code-reviewer (F3/P2) — explicit number: field must be read here so both
        // enforcement paths (--check mode and Audit 5) derive the same number from the same
        // source; previously absent, causing divergence when number != trailing stub_id integer.
        number: (fm.number !== undefined && fm.number !== null) ? Number(fm.number) : null,
        sprint: (fm.sprint !== undefined && fm.sprint !== null) ? Number(fm.sprint) : null,
        wave:   (fm.wave   !== undefined && fm.wave   !== null) ? Number(fm.wave)   : null,
        blocked_by: Array.isArray(fm.blocked_by) ? fm.blocked_by : (fm.blocked_by ? [String(fm.blocked_by)] : []),
      };
      if (entry.stub_id) process.stdout.write(JSON.stringify(entry) + '\n');
    " -- "$_LIB_DIR" "$DATA_ROOT" "$p" 2>/dev/null || true
  done)

  if [ -z "$A5_STUBS_JSON" ]; then
    pass "Audit 5: stubs found but none carried a parseable stub_id — dependency-order check skipped."
  else
    # Pass the newline-delimited JSON objects to a node checker that wraps each line
    # into an array and calls checkDependencyOrder from roadmap-graph.js.
    # argv[1]=_LIB_DIR (require path for roadmap-graph.js)
    A5_RESULT=$(printf '%s\n' "$A5_STUBS_JSON" | node -e "// verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
      const path=require('path');
      const {checkDependencyOrder} = require(path.join(process.argv[1], 'roadmap-graph.js'));
      let raw='';
      process.stdin.on('data', function(c){ raw+=c; });
      process.stdin.on('end', function(){
        const stubs = raw.trim().split('\n').filter(Boolean).map(function(l){ return JSON.parse(l); });
        const result = checkDependencyOrder(stubs);
        process.stdout.write(JSON.stringify(result) + '\n');
      });
    " -- "$_LIB_DIR" 2>/dev/null || echo '{"ok":false,"violations":[],"unresolved":[],"cycle":null,"_error":"node invocation failed"}')

    # Parse and report from the JSON result in bash via a node one-liner for portability.
    A5_OK=$(echo "$A5_RESULT" | node -e "// verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
      let d=''; process.stdin.on('data',function(c){d+=c;}).on('end',function(){ console.log(JSON.parse(d).ok ? 'true' : 'false'); });
    " -- "$_LIB_DIR" 2>/dev/null || echo "false")

    A5_STUB_COUNT=$(printf '%s\n' "$A5_STUBS_JSON" | grep -c . || true)
    A5_EDGE_COUNT=$(printf '%s\n' "$A5_STUBS_JSON" | node -e "// verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
      let d=''; process.stdin.on('data',function(c){d+=c;}).on('end',function(){
        const stubs=d.trim().split('\n').filter(Boolean).map(function(l){return JSON.parse(l);});
        const total=stubs.reduce(function(s,st){return s+(st.blocked_by||[]).length;},0);
        console.log(total);
      });
    " -- "$_LIB_DIR" 2>/dev/null || echo "0")

    if [ "$A5_OK" = "true" ]; then
      pass "Audit 5: dependency-order invariant holds for roadmap_id=${RUN_ID} (${A5_EDGE_COUNT} edges checked across ${A5_STUB_COUNT} stubs)."
    else
      # Report each violation and unresolved edge individually.
      # IMPORTANT: use process substitution < <(...) NOT a pipe | while, so the while loop
      # runs in the parent shell and fail()'s EXIT_CODE=1 assignment propagates correctly.
      # A pipe-into-while runs the loop body in a subshell — EXIT_CODE stays 0 in the
      # parent and the gate silently lets bad roadmaps through (dead-gate bug).
      while IFS= read -r line; do
        # Lines already contain "FAIL: " prefix from node stderr — re-emit via fail() to
        # set EXIT_CODE and keep output on stderr, stripping the embedded "FAIL: " prefix.
        msg="${line#FAIL: }"
        fail "$msg"
      done < <(echo "$A5_RESULT" | node -e "// verify-no-console-flash: allow — on-demand roadmap audit, not session-hot-path
        let d=''; process.stdin.on('data',function(c){d+=c;}).on('end',function(){
          const r=JSON.parse(d);
          // Violations
          (r.violations||[]).forEach(function(v){
            if (v.reason==='missing-sprint') {
              process.stderr.write('FAIL: Audit 5: dependency-order violation — ' + v.from + ' blocked_by ' + v.to + ' but sprint missing on ' + v.which + ' endpoint\n');
            } else if (v.reason==='number-order') {
              process.stderr.write('FAIL: Audit 5: dependency-order violation — ' + v.from + ' (N=' + v.numberA + ') blocked_by ' + v.to + ' (N=' + v.numberB + ') but number(dep) >= number(dependent); expected number(' + v.to + ') < number(' + v.from + ')\n');
            } else if (v.reason==='same-or-inverted-slot') {
              process.stderr.write('FAIL: Audit 5: dependency-order violation — ' + v.from + ' (sprint=' + v.slotA.sprint + ',wave=' + v.slotA.wave + ') blocked_by ' + v.to + ' (sprint=' + v.slotB.sprint + ',wave=' + v.slotB.wave + ') but (sprint,wave) slot of dep is not strictly less than dependent\n');
            } else {
              process.stderr.write('FAIL: Audit 5: dependency-order violation — ' + v.from + ' blocked_by ' + v.to + ' (' + v.reason + ')\n');
            }
          });
          // Unresolved edges
          (r.unresolved||[]).forEach(function(u){
            process.stderr.write('FAIL: Audit 5: unresolved blocked_by edge — ' + u.from + ' depends on ' + u.to + ' which is not in the roadmap_id=' + process.argv[1] + ' stub set\n');
          });
          // Cycle
          if (r.cycle && r.cycle.length) {
            process.stderr.write('FAIL: Audit 5: dependency cycle detected among stubs: ' + r.cycle.join(' → ') + '\n');
          }
          // Node invocation error passthrough
          if (r._error) {
            process.stderr.write('FAIL: Audit 5: checkDependencyOrder invocation error — ' + r._error + '\n');
          }
        });
      " -- "$RUN_ID" 2>&1)
    fi
  fi
fi

# --- Summary --------------------------------------------------------------
echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "audit-roadmap: all checks passed for roadmap_id=${RUN_ID}"
else
  echo "audit-roadmap: one or more checks FAILED for roadmap_id=${RUN_ID} — Phase 3 dispatch is blocked"
fi
exit "$EXIT_CODE"
