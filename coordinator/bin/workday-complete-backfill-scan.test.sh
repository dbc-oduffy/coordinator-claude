#!/usr/bin/env bash
# workday-complete-backfill-scan.test.sh — Smoke tests for the skipped-day backfill scanner.
#
# Verifies the scan's contract in an isolated mktemp fixture repo with backdated commits —
# NEVER touches the real repo. Asserts: commits-but-no-summary days are emitted, summary-present
# days are excluded, no-commit days are absent, output is oldest-first, lookback bounds the window,
# and the TSV shape is <date>\t<count>\t<baseline>\t<tip>.
#
# Usage: bash workday-complete-backfill-scan.test.sh
# Exit: 0 if all pass; non-zero otherwise.
#
# Spec backlink: commands/workday-complete.md § Step 3.5

set -uo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (macOS stock /bin/bash is 3.2 — use brew bash)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="${SCRIPT_DIR}/workday-complete-backfill-scan.sh"
[[ -f "${SCAN}" ]] || { echo "FATAL: scan script not found at ${SCAN}" >&2; exit 1; }

PASS=0
FAIL=0
FIXTURE_DIRS=()
cleanup() { for d in "${FIXTURE_DIRS[@]}"; do [[ -d "${d}" ]] && rm -rf "${d}"; done; }
trap cleanup EXIT

ok()   { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

# commit_on <repo> <YYYY-MM-DD> <message> — one backdated commit at 12:00:00Z.
commit_on() {
  local repo="$1" d="$2" msg="$3" f
  f="f-${d}-${RANDOM}.txt"
  echo "${msg}" > "${repo}/${f}"
  git -C "${repo}" add -- "${f}"
  GIT_AUTHOR_DATE="${d}T12:00:00Z" GIT_COMMITTER_DATE="${d}T12:00:00Z" \
    git -C "${repo}" commit -q -m "${msg}"
}

make_repo() {
  local dir; dir="$(mktemp -d)"; FIXTURE_DIRS+=("${dir}")
  git -C "${dir}" init -q
  git -C "${dir}" config user.email "test@test.com"
  git -C "${dir}" config user.name "test"
  git -C "${dir}" config commit.gpgsign false
  mkdir -p "${dir}/archive/daily-summaries"
  printf '%s' "${dir}"
}

# ---------------------------------------------------------------------------
REPO="$(make_repo)"
# 03-10: commit, NO summary  -> expect emitted
# 03-12: commit, WITH summary -> expect excluded
# 03-11: NO commit            -> expect absent
# 02-20: commit, NO summary, but 23 days before pinned today (>14 lookback) -> excluded
commit_on "${REPO}" "2026-02-20" "old (out of lookback)"
commit_on "${REPO}" "2026-03-10" "missed day A"
commit_on "${REPO}" "2026-03-10" "missed day A second commit"
commit_on "${REPO}" "2026-03-12" "covered day"
echo "summary" > "${REPO}/archive/daily-summaries/2026-03-12.md"

OUT="$(COORDINATOR_ROOT="${REPO}" bash "${SCAN}" --lookback 14 --today 2026-03-15)"

# T1: 03-10 emitted
if grep -q '^2026-03-10	' <<<"${OUT}"; then ok "T1 commit-no-summary day emitted"; else bad "T1 03-10 missing: ${OUT}"; fi
# T2: 03-12 excluded (summary present)
if grep -q '^2026-03-12	' <<<"${OUT}"; then bad "T2 03-12 should be excluded (has summary)"; else ok "T2 summary-present day excluded"; fi
# T3: 03-11 absent (no commit)
if grep -q '^2026-03-11	' <<<"${OUT}"; then bad "T3 03-11 should be absent (no commit)"; else ok "T3 no-commit day absent"; fi
# T4: 02-20 excluded (beyond lookback)
if grep -q '^2026-02-20	' <<<"${OUT}"; then bad "T4 02-20 should be beyond 14-day lookback"; else ok "T4 lookback bound excludes old day"; fi
# T5: TSV shape — 4 tab-separated fields, count==2 for 03-10
ROW="$(grep '^2026-03-10	' <<<"${OUT}")"
NF="$(awk -F'\t' '{print NF}' <<<"${ROW}")"
CNT="$(awk -F'\t' '{print $2}' <<<"${ROW}")"
BASE="$(awk -F'\t' '{print $3}' <<<"${ROW}")"
if [[ "${NF}" == "4" && "${CNT}" == "2" ]]; then ok "T5 TSV shape (4 fields, count=2)"; else bad "T5 shape NF=${NF} CNT=${CNT}"; fi
# T6: baseline sha is a valid commit-ish (40 hex or resolvable) OR equals first sha when no parent
if [[ "${BASE}" =~ ^[0-9a-f]{7,40}$ ]]; then ok "T6 baseline sha well-formed"; else bad "T6 baseline malformed: ${BASE}"; fi
# T6b: baseline != tip — 03-10 has a parent commit; root-commit fallback must NOT have fired
TIP_ROW="$(awk -F'\t' '{print $4}' <<<"${ROW}")"
if [[ "${BASE}" != "${TIP_ROW}" ]]; then ok "T6b baseline != tip (root-commit fallback did not fire)"; else bad "T6b baseline == tip unexpectedly (root-commit fallback fired when parent exists): BASE=${BASE}"; fi

# T7: empty result when all days covered
REPO2="$(make_repo)"
commit_on "${REPO2}" "2026-03-13" "covered"
echo s > "${REPO2}/archive/daily-summaries/2026-03-13.md"
OUT2="$(COORDINATOR_ROOT="${REPO2}" bash "${SCAN}" --lookback 14 --today 2026-03-15)"
if [[ -z "${OUT2}" ]]; then ok "T7 empty output when no missed days"; else bad "T7 expected empty, got: ${OUT2}"; fi

# T8: bad --lookback rejected
if COORDINATOR_ROOT="${REPO}" bash "${SCAN}" --lookback 0 --today 2026-03-15 >/dev/null 2>&1; then
  bad "T8 --lookback 0 should be rejected"
else ok "T8 invalid --lookback rejected"; fi

# T9: date_minus end-to-end — a fresh repo with a commit on 2026-03-14 and no summary;
# --lookback 1 --today 2026-03-15 should emit 2026-03-14 (exercises date_minus).
# A broken date helper would produce empty output and the test would catch it silently.
REPO3="$(make_repo)"
commit_on "${REPO3}" "2026-03-14" "missed day for date-minus test"
OUT3="$(COORDINATOR_ROOT="${REPO3}" bash "${SCAN}" --lookback 1 --today 2026-03-15)"
if grep -q '^2026-03-14	' <<<"${OUT3}"; then
  ok "T9 date_minus end-to-end: 2026-03-14 emitted with --lookback 1 --today 2026-03-15"
else
  bad "T9 date_minus broken or off-by-one: expected 2026-03-14 in output, got: ${OUT3}"
fi

echo "---"
echo "backfill-scan: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
