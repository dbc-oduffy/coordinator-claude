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

set -euo pipefail

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

# AC4: late-morning wrap of prior day (rolling-window-floor)
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

# ---------------------------------------------------------------------------
# TM tests: per-machine predicate (requires work/{machine}/* branches in repo)
# Spec backlink: docs/plans/2026-07-01-workday-complete-multi-machine-coverage.md § C2
# ---------------------------------------------------------------------------

# Helper: create an orphan branch, make a backdated commit, return to caller's branch.
# Usage: init_branch_commit <repo> <branch> <YYYY-MM-DD> <HH:MM:SSZ> <msg> → prints SHA
init_branch_commit() {
  local repo="$1" branch="$2" d="$3" t="$4" msg="$5"
  git -C "${repo}" checkout --orphan "${branch}" -q 2>/dev/null || \
    git -C "${repo}" checkout -b "${branch}" -q 2>/dev/null
  # Unstage any files carried over from --orphan (safe to ignore errors on fresh repo)
  git -C "${repo}" rm -rf --cached . -q 2>/dev/null || true
  local f="f-${RANDOM}.txt"
  echo "${msg}" > "${repo}/${f}"
  git -C "${repo}" add -- "${f}"
  GIT_AUTHOR_DATE="${d}T${t}" GIT_COMMITTER_DATE="${d}T${t}" \
    git -C "${repo}" commit -q -m "${msg}"
  git -C "${repo}" rev-parse HEAD
}

# TM1: Canonical M2-older case.
# M1 commits on 2026-03-13, summary records M1's tip.
# M2 commits on 2026-03-13 via span-named branch work/m2/2026-03-10 (earlier in day).
# A global-tip check would see M1's tip covered → false-pass. Per-machine must flag M2.
REPO_TM1="$(make_repo)"
SHA_M1="$(init_branch_commit "${REPO_TM1}" work/m1/2026-03-13 2026-03-13 14:00:00Z "m1 commit")"
SHA_M2="$(init_branch_commit "${REPO_TM1}" work/m2/2026-03-10 2026-03-13 10:00:00Z "m2 commit (span-named branch)")"
printf 'covered_tip_sha: %s\ncovered_machine: m1\n' "${SHA_M1}" \
  > "${REPO_TM1}/archive/daily-summaries/2026-03-13-m1.md"
OUT_TM1="$(COORDINATOR_ROOT="${REPO_TM1}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-14)"

if printf '%s\n' "${OUT_TM1}" | grep -q $'^2026-03-13\tm2\t'; then
  ok "TM1a M2 flagged (span-named branch, no coverage)"
else bad "TM1a M2 not flagged — out: ${OUT_TM1}"; fi
if printf '%s\n' "${OUT_TM1}" | grep -q $'^2026-03-13\tm1\t'; then
  bad "TM1b M1 falsely flagged — out: ${OUT_TM1}"
else ok "TM1b M1 not flagged (covered with correct tip)"; fi

# AC3: post-wrap same-day commit → stale-tip case
# TM2: Stale-tip case.
# M1 has two commits (C1, C2) on 2026-03-14; summary records C1 (ancestor of C2) → GAP.
REPO_TM2="$(make_repo)"
# First commit (C1) on work/m1/2026-03-14
git -C "${REPO_TM2}" symbolic-ref HEAD refs/heads/work/m1/2026-03-14
echo "c1" > "${REPO_TM2}/c1.txt"
git -C "${REPO_TM2}" add -- c1.txt
GIT_AUTHOR_DATE="2026-03-14T10:00:00Z" GIT_COMMITTER_DATE="2026-03-14T10:00:00Z" \
  git -C "${REPO_TM2}" commit -q -m "m1 C1"
SHA_C1="$(git -C "${REPO_TM2}" rev-parse HEAD)"
# Second commit (C2) on same branch
echo "c2" > "${REPO_TM2}/c2.txt"
git -C "${REPO_TM2}" add -- c2.txt
GIT_AUTHOR_DATE="2026-03-14T18:00:00Z" GIT_COMMITTER_DATE="2026-03-14T18:00:00Z" \
  git -C "${REPO_TM2}" commit -q -m "m1 C2"
SHA_C2="$(git -C "${REPO_TM2}" rev-parse HEAD)"
# Summary records C1 (stale)
printf 'covered_tip_sha: %s\ncovered_machine: m1\n' "${SHA_C1}" \
  > "${REPO_TM2}/archive/daily-summaries/2026-03-14-m1.md"
OUT_TM2="$(COORDINATOR_ROOT="${REPO_TM2}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-15)"
if printf '%s\n' "${OUT_TM2}" | grep -q $'^2026-03-14\tm1\t'; then
  ok "TM2 stale-tip flagged (recorded is ancestor of actual tip)"
else bad "TM2 stale-tip not flagged — out: ${OUT_TM2}"; fi

# TM3: Missing covered_tip_sha field → GAP.
REPO_TM3="$(make_repo)"
SHA_TM3="$(init_branch_commit "${REPO_TM3}" work/m1/2026-03-14 2026-03-14 12:00:00Z "m1 commit")"
# Summary exists but has no covered_tip_sha
printf 'covered_machine: m1\n# no covered_tip_sha here\n' \
  > "${REPO_TM3}/archive/daily-summaries/2026-03-14-m1.md"
OUT_TM3="$(COORDINATOR_ROOT="${REPO_TM3}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-15)"
if printf '%s\n' "${OUT_TM3}" | grep -q $'^2026-03-14\tm1\t'; then
  ok "TM3 missing covered_tip_sha flagged"
else bad "TM3 missing covered_tip_sha not flagged — out: ${OUT_TM3}"; fi

# TM4: Fully covered — both machines recorded with exact tips → no output.
REPO_TM4="$(make_repo)"
SHA_TM4_M1="$(init_branch_commit "${REPO_TM4}" work/m1/2026-03-13 2026-03-13 14:00:00Z "m1 commit")"
SHA_TM4_M2="$(init_branch_commit "${REPO_TM4}" work/m2/2026-03-12 2026-03-13 10:00:00Z "m2 commit")"
printf 'covered_tip_sha: %s\ncovered_machine: m1\n' "${SHA_TM4_M1}" \
  > "${REPO_TM4}/archive/daily-summaries/2026-03-13-m1.md"
printf 'covered_tip_sha: %s\ncovered_machine: m2\n' "${SHA_TM4_M2}" \
  > "${REPO_TM4}/archive/daily-summaries/2026-03-13-m2.md"
OUT_TM4="$(COORDINATOR_ROOT="${REPO_TM4}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-14)"
if [[ -z "${OUT_TM4}" ]]; then
  ok "TM4 fully covered — no output (both machines recorded with exact tips)"
else bad "TM4 expected empty output, got: ${OUT_TM4}"; fi

# TM5: Reconcile-only machine — a real merge (NOT orphan histories) makes m2's commit
# reachable from m1's branch without m1 authoring anything. Per-machine tip-walk
# (--no-merges log over m1's own branch) picks up m2's foreign commit as m1's "tip",
# and the missing-summary gap check would flag m1 for work it never did. The
# exclusive-commit gate (rev-list <tip> ^<other-refs>, day-window-scoped) must suppress
# the false-positive row for m1 while m2 — which authored the real work and has a
# summary recording its own tip — is correctly handled as covered (absent from output).
# Note: once m1 merges m2's commit, that commit is reachable from BOTH branches, so an
# UNCOVERED m2 would also be suppressed by the same exclusivity check applied to its own
# row — that is the fix's inherent git-reachability semantics (a merged-in commit is no
# longer exclusive to either side), not a fixture defect. Giving m2 a covered_tip_sha
# summary here isolates the assertion to "gate doesn't over-suppress a machine with its
# own recorded coverage" per fix3-report.md §4's "delphipro covered-and-absent" option.
# init_branch_commit's --orphan histories cannot reproduce this — a real merge is required.
# Spec backlink: coordinator-bin/fix3-report.md § 3-4 (2026-07-06 backfill-scan
# multimachine-false-positive fix)
# Shared root commit so the reconcile merge is a real ancestry merge (not
# --allow-unrelated-histories, which would be an unrealistic fixture shape).
REPO_TM5="$(make_repo)"
echo "root" > "${REPO_TM5}/root.txt"
git -C "${REPO_TM5}" add -- root.txt
GIT_AUTHOR_DATE="2026-03-12T09:00:00Z" GIT_COMMITTER_DATE="2026-03-12T09:00:00Z" \
  git -C "${REPO_TM5}" commit -q -m "shared root"
SHA_TM5_ROOT="$(git -C "${REPO_TM5}" rev-parse HEAD)"
git -C "${REPO_TM5}" branch work/m2/2026-03-14 -q
git -C "${REPO_TM5}" checkout work/m2/2026-03-14 -q
echo "m2 work" > "${REPO_TM5}/m2-work.txt"
git -C "${REPO_TM5}" add -- m2-work.txt
GIT_AUTHOR_DATE="2026-03-14T09:00:00Z" GIT_COMMITTER_DATE="2026-03-14T09:00:00Z" \
  git -C "${REPO_TM5}" commit -q -m "m2 commit (authored)"
SHA_TM5_M2="$(git -C "${REPO_TM5}" rev-parse HEAD)"
printf 'covered_tip_sha: %s\ncovered_machine: m2\n' "${SHA_TM5_M2}" \
  > "${REPO_TM5}/archive/daily-summaries/2026-03-14-m2.md"
git -C "${REPO_TM5}" checkout -b work/m1/2026-03-14 "${SHA_TM5_ROOT}" -q
echo "m1 initial" > "${REPO_TM5}/m1-init.txt"
git -C "${REPO_TM5}" add -- m1-init.txt
GIT_AUTHOR_DATE="2026-03-13T10:00:00Z" GIT_COMMITTER_DATE="2026-03-13T10:00:00Z" \
  git -C "${REPO_TM5}" commit -q -m "m1 initial (prior day, outside window)"
# m1 reconciles m2's work into its own branch via a real (non-fast-forward) merge,
# backdated into the D window — this is what makes SHA_TM5_M2 reachable from m1's tip
# WITHOUT m1 authoring any commit inside the window.
GIT_AUTHOR_DATE="2026-03-14T20:00:00Z" GIT_COMMITTER_DATE="2026-03-14T20:00:00Z" \
  git -C "${REPO_TM5}" merge --no-ff -q -m "m1 reconcile merge of m2" "${SHA_TM5_M2}"
OUT_TM5="$(COORDINATOR_ROOT="${REPO_TM5}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-15 2>/tmp/tm5-stderr.$$)"
ERR_TM5="$(cat /tmp/tm5-stderr.$$ 2>/dev/null || true)"; rm -f /tmp/tm5-stderr.$$
if printf '%s\n' "${OUT_TM5}" | grep -q $'^2026-03-14\tm1\t'; then
  bad "TM5a m1 (reconcile-only) falsely flagged — out: ${OUT_TM5}"
else ok "TM5a m1 (reconcile-only) NOT flagged (exclusive-commit gate suppressed it)"; fi
if printf '%s\n' "${OUT_TM5}" | grep -q $'^2026-03-14\tm2\t'; then
  bad "TM5b m2 (authored, covered by its own summary) unexpectedly flagged — out: ${OUT_TM5}"
else ok "TM5b m2 (authored, covered-and-absent) correctly handled — not over-suppressed into a false gap"; fi
if printf '%s\n' "${ERR_TM5}" | grep -q 'NO-EXCLUSIVE-WORK'; then
  ok "TM5c NO-EXCLUSIVE-WORK informational line emitted for m1"
else bad "TM5c NO-EXCLUSIVE-WORK line missing — stderr: ${ERR_TM5}"; fi

# TM6: Documented false-negative — m2 is UNCOVERED (no covered_tip_sha summary at all)
# and its commit is merged into m1 via a real (non-fast-forward) merge, exactly as in
# TM5. Unlike TM5 (which gives m2 its own summary to isolate the "gate doesn't
# over-suppress a covered machine" assertion), TM6 leaves m2 with NO summary so the
# suite actually exercises the false-negative the header comment and fix3-report.md
# describe: once m1 merges m2's commit, that commit is reachable from BOTH branches,
# so the same exclusivity check that correctly suppresses m1's reconcile-only row also
# suppresses m2's row — even though m2 authored real, uncovered work. This IS the
# documented, accepted tradeoff (see Judgment call 1 in the 2026-07-09
# ceremony-tooling-bugfix-bundle review) — NOT a false pass. The assertion below locks
# CURRENT ACCEPTED behavior (no gap row for m2) as a regression-guarded contract: a
# future change to the exclusivity predicate that silently widens or narrows this
# false-negative surface will now fail a test instead of going unnoticed.
# Spec backlink: coordinator-bin/fix3-report.md § 3-4; state/review-trail/findings/
# 2026-07-09-codereview-sliceceremony-tooling-bugfix-bundle-coordinator-skills-workstream-complete-s.md
# Finding 1 (P2).
# Reuses TM5's real-merge fixture technique (NOT --orphan branches, which cannot
# reproduce a reachable, non-fast-forward merge).
REPO_TM6="$(make_repo)"
echo "root" > "${REPO_TM6}/root.txt"
git -C "${REPO_TM6}" add -- root.txt
GIT_AUTHOR_DATE="2026-03-12T09:00:00Z" GIT_COMMITTER_DATE="2026-03-12T09:00:00Z" \
  git -C "${REPO_TM6}" commit -q -m "shared root"
SHA_TM6_ROOT="$(git -C "${REPO_TM6}" rev-parse HEAD)"
git -C "${REPO_TM6}" branch work/m2/2026-03-14 -q
git -C "${REPO_TM6}" checkout work/m2/2026-03-14 -q
echo "m2 work" > "${REPO_TM6}/m2-work.txt"
git -C "${REPO_TM6}" add -- m2-work.txt
GIT_AUTHOR_DATE="2026-03-14T09:00:00Z" GIT_COMMITTER_DATE="2026-03-14T09:00:00Z" \
  git -C "${REPO_TM6}" commit -q -m "m2 commit (authored, UNCOVERED — no summary written)"
SHA_TM6_M2="$(git -C "${REPO_TM6}" rev-parse HEAD)"
# Deliberately do NOT write archive/daily-summaries/2026-03-14-m2.md — m2 stays uncovered.
git -C "${REPO_TM6}" checkout -b work/m1/2026-03-14 "${SHA_TM6_ROOT}" -q
echo "m1 initial" > "${REPO_TM6}/m1-init.txt"
git -C "${REPO_TM6}" add -- m1-init.txt
GIT_AUTHOR_DATE="2026-03-13T10:00:00Z" GIT_COMMITTER_DATE="2026-03-13T10:00:00Z" \
  git -C "${REPO_TM6}" commit -q -m "m1 initial (prior day, outside window)"
GIT_AUTHOR_DATE="2026-03-14T20:00:00Z" GIT_COMMITTER_DATE="2026-03-14T20:00:00Z" \
  git -C "${REPO_TM6}" merge --no-ff -q -m "m1 reconcile merge of m2" "${SHA_TM6_M2}"
OUT_TM6="$(COORDINATOR_ROOT="${REPO_TM6}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-15 2>/tmp/tm6-stderr.$$)"
ERR_TM6="$(cat /tmp/tm6-stderr.$$ 2>/dev/null || true)"; rm -f /tmp/tm6-stderr.$$
if printf '%s\n' "${OUT_TM6}" | grep -q $'^2026-03-14\tm2\t'; then
  bad "TM6a m2 (uncovered, merged-in, no summary) unexpectedly flagged — the documented false-negative regressed (gate stopped over-suppressing): out: ${OUT_TM6}"
else ok "TM6a m2 (uncovered, merged-in, no summary) correctly NOT flagged — this is the documented false-negative (merged-in commit no longer exclusive to m2), not a false pass"; fi
if printf '%s\n' "${OUT_TM6}" | grep -q $'^2026-03-14\tm1\t'; then
  bad "TM6b m1 (reconcile-only) falsely flagged — out: ${OUT_TM6}"
else ok "TM6b m1 (reconcile-only) NOT flagged (exclusive-commit gate suppressed it, as in TM5a)"; fi

# ---------------------------------------------------------------------------
# TM7: Cross-machine main-exclusion — the false-positive this fix closes.
# A "wrapping" machine (mwrap) authors an in-window commit and merges its work/* branch
# to main; mwrap's work/* branch is then pruned (simulated by simply never giving mwrap
# any work/* ref at scan time — only main carries its commit). A second machine m1 has
# its OWN work/* branch, reconciled from main AFTER mwrap's commit landed there, so
# mwrap's commit is reachable from m1's tip via main but m1 authored NO in-window work
# and wrote no daily summary.
#
# Before this fix (no ^main/^origin-main in _excl), rev-list <m1 tip> ^<other work/*
# refs> would NOT subtract main, so mwrap's commit — inherited via main, not authored by
# m1 — would count as "exclusive" to m1 (no other work/* ref reaches it, since mwrap has
# none) and m1 would be falsely flagged as an uncloseable gap on every run. After this
# fix, main is subtracted too, so the inherited commit is no longer exclusive to m1 and
# the NO-EXCLUSIVE-WORK path fires instead.
# Spec backlink: state/handoffs/2026-07-10_002326_backfill-scan-cross-machine-main-exclusion.md
# ---------------------------------------------------------------------------
REPO_TM7="$(make_repo)"
echo "root" > "${REPO_TM7}/root.txt"
git -C "${REPO_TM7}" add -- root.txt
GIT_AUTHOR_DATE="2026-03-12T09:00:00Z" GIT_COMMITTER_DATE="2026-03-12T09:00:00Z" \
  git -C "${REPO_TM7}" commit -q -m "shared root"
SHA_TM7_ROOT="$(git -C "${REPO_TM7}" rev-parse HEAD)"
# mwrap authors its in-window commit directly on main (simulating "merged to main, then
# work/* pruned" — from the scanner's perspective at scan time, the commit is reachable
# ONLY from main, exactly as it would be post-merge-and-prune).
git -C "${REPO_TM7}" checkout main -q 2>/dev/null || git -C "${REPO_TM7}" checkout -b main -q
echo "mwrap work" > "${REPO_TM7}/mwrap-work.txt"
git -C "${REPO_TM7}" add -- mwrap-work.txt
GIT_AUTHOR_DATE="2026-03-14T09:00:00Z" GIT_COMMITTER_DATE="2026-03-14T09:00:00Z" \
  git -C "${REPO_TM7}" commit -q -m "mwrap commit (authored, merged-to-main, branch pruned)"
SHA_TM7_MWRAP="$(git -C "${REPO_TM7}" rev-parse HEAD)"
# m1 branches from main AFTER mwrap's commit landed — mwrap's commit is reachable from
# m1's tip via ordinary ancestry (no merge commit needed; ff-branch off main suffices),
# but m1 authors nothing new in-window and writes no summary.
git -C "${REPO_TM7}" checkout -b work/m1/2026-03-14 "${SHA_TM7_MWRAP}" -q
OUT_TM7="$(COORDINATOR_ROOT="${REPO_TM7}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-15 2>/tmp/tm7-stderr.$$)"
ERR_TM7="$(cat /tmp/tm7-stderr.$$ 2>/dev/null || true)"; rm -f /tmp/tm7-stderr.$$
if printf '%s\n' "${OUT_TM7}" | grep -q $'^2026-03-14\tm1\t'; then
  bad "TM7a m1 (main-inherited, not exclusive) falsely flagged — out: ${OUT_TM7}"
else ok "TM7a m1 (main-inherited, not exclusive) NOT flagged (main-subtraction gate suppressed it)"; fi
if printf '%s\n' "${ERR_TM7}" | grep -q 'NO-EXCLUSIVE-WORK'; then
  ok "TM7b NO-EXCLUSIVE-WORK informational line emitted for m1"
else bad "TM7b NO-EXCLUSIVE-WORK line missing — stderr: ${ERR_TM7}"; fi

# ---------------------------------------------------------------------------
# TM8: Complementary — genuine exclusive work is STILL flagged after the main-exclusion
# fix (no over-suppression). m1 authors real in-window work that stays only on its own
# work/* branch (never reachable from main), with no daily summary. This proves
# subtracting main does not swallow real gaps beyond the ratified TM7-shaped tradeoff.
# Spec backlink: state/handoffs/2026-07-10_002326_backfill-scan-cross-machine-main-exclusion.md
# ---------------------------------------------------------------------------
REPO_TM8="$(make_repo)"
echo "root" > "${REPO_TM8}/root.txt"
git -C "${REPO_TM8}" add -- root.txt
GIT_AUTHOR_DATE="2026-03-12T09:00:00Z" GIT_COMMITTER_DATE="2026-03-12T09:00:00Z" \
  git -C "${REPO_TM8}" commit -q -m "shared root"
SHA_TM8_ROOT="$(git -C "${REPO_TM8}" rev-parse HEAD)"
git -C "${REPO_TM8}" checkout main -q 2>/dev/null || git -C "${REPO_TM8}" checkout -b main -q
git -C "${REPO_TM8}" checkout -b work/m1/2026-03-14 "${SHA_TM8_ROOT}" -q
echo "m1 exclusive work" > "${REPO_TM8}/m1-exclusive.txt"
git -C "${REPO_TM8}" add -- m1-exclusive.txt
GIT_AUTHOR_DATE="2026-03-14T09:00:00Z" GIT_COMMITTER_DATE="2026-03-14T09:00:00Z" \
  git -C "${REPO_TM8}" commit -q -m "m1 commit (authored, never merged to main, no summary)"
OUT_TM8="$(COORDINATOR_ROOT="${REPO_TM8}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-15)"
if printf '%s\n' "${OUT_TM8}" | grep -q $'^2026-03-14\tm1\t'; then
  ok "TM8 m1 (genuine exclusive work, not on main) correctly flagged — not over-suppressed"
else bad "TM8 m1 expected to be flagged as a gap, got: ${OUT_TM8}"; fi

# ---------------------------------------------------------------------------
# TD tests: dangling-defer pointer guard
# Spec backlink: docs/wiki/daily-summary-procedure.md § Machine-Defer Convention
# ---------------------------------------------------------------------------

# TD1: Summary defers to machine X AND <date>-X.md changelog exists → NOT flagged as dangling.
REPO_TD1="$(make_repo)"
SHA_TD1="$(init_branch_commit "${REPO_TD1}" work/mach1/2026-03-25 2026-03-25 12:00:00Z "td1 commit")"
mkdir -p "${REPO_TD1}/state/week-changelog"
# Summary records its own tip AND declares a valid defer to othermach
printf 'covered_tip_sha: %s\ncovered_machine: mach1\ndefers_to: othermach\n' "${SHA_TD1}" \
  > "${REPO_TD1}/archive/daily-summaries/2026-03-25-mach1.md"
# Create the referenced changelog so the defer is valid
touch "${REPO_TD1}/state/week-changelog/2026-03-25-othermach.md"
OUT_TD1="$(COORDINATOR_ROOT="${REPO_TD1}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-26 2>&1)"
if echo "${OUT_TD1}" | grep -q 'DANGLING-DEFER'; then
  bad "TD1 valid defer incorrectly flagged as dangling: ${OUT_TD1}"
else ok "TD1 valid defer (target changelog exists) — not flagged as dangling"; fi

# TD2: Summary defers to machine X but <date>-X.md changelog is ABSENT → flagged loud.
REPO_TD2="$(make_repo)"
SHA_TD2="$(init_branch_commit "${REPO_TD2}" work/mach1/2026-03-26 2026-03-26 12:00:00Z "td2 commit")"
mkdir -p "${REPO_TD2}/state/week-changelog"
# Summary declares a defer to othermach but the changelog file is intentionally absent
printf 'covered_tip_sha: %s\ncovered_machine: mach1\ndefers_to: othermach\n' "${SHA_TD2}" \
  > "${REPO_TD2}/archive/daily-summaries/2026-03-26-mach1.md"
OUT_TD2="$(COORDINATOR_ROOT="${REPO_TD2}" COORDINATOR_ROOT_WARN_SUPPRESS=1 \
  bash "${SCAN}" --lookback 1 --today 2026-03-27 2>&1)"
if echo "${OUT_TD2}" | grep -q 'DANGLING-DEFER'; then
  ok "TD2 dangling defer flagged loud (target changelog absent)"
else bad "TD2 dangling defer not flagged — out: ${OUT_TD2}"; fi

echo "---"
echo "backfill-scan: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
