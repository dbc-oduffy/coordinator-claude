#!/usr/bin/env bash
# close-origin-stub-on-ship.test.sh — self-contained tests for
# bin/close-origin-stub-on-ship.sh.
#
# Spec backlink: cross-repo/inbox/2026-07-08-example-cockpit-repo-em-spinoff-roadmap-lifecycle-never-closed.md
#
# The subject's join logic (steps 1-5) is exercised for real against fixture
# stub files under a temp state/handoffs/ directory and a fixture governing
# plan. The final coordinator-handoff-archive.sh --stamp-only invocation is
# shimmed via a PATH-injected fake so the join logic's SELECTION can be
# asserted (which stub path it decided to stamp) without needing a full git
# repo + live-children guard + stamp lib for every case.
#
# Test coverage:
#   T1  matching ready_to_fire stub          — selected, stamp invoked on right path
#   T2  plan with no stub_id                 — no-op, exit 0
#   T3  stub already deployment_state:shipped — NOT selected (excluded, no stamp)
#   T4  in_flight stub with matching (rid,sid) — NOT selected (Step 2.7's job)
#   T5  two stubs sharing the same (rid,sid)  — ambiguity warning, no stamp
#   T6  quoted stub_id containing "#" is extracted in full (regression guard
#       for the comment-strip-before-quote-strip bug), and an unquoted value
#       with a legitimate trailing " # comment" is still stripped correctly
#
# Usage: bash <this-file>
# Exit:  0 if all tests pass, non-zero on any failure.

set -euo pipefail

if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBJECT="${SCRIPT_DIR}/close-origin-stub-on-ship.sh"

if [[ ! -f "$SUBJECT" ]]; then
  echo "ERROR: subject not found: $SUBJECT" >&2
  exit 1
fi

PASS=0
FAIL=0
_pass() { echo "PASS: $1"; PASS=$(( PASS + 1 )); }
_fail() { echo "FAIL: $1 — $2"; FAIL=$(( FAIL + 1 )); }

TMPBASE=$(mktemp -d)
trap 'rm -rf "$TMPBASE"' EXIT

# ---------------------------------------------------------------------------
# _make_fixture DIR — build a working dir with state/handoffs/ and a fake
# PATH-shimmed coordinator-handoff-archive.sh that logs its invocation
# (path + flags) to $DIR/stamp-calls.log and exits 0, so the join logic's
# selection can be asserted without a live git repo / stamp lib.
# ---------------------------------------------------------------------------
_make_fixture() {
  local base="$1"
  mkdir -p "$base/state/handoffs"
  mkdir -p "$base/fakebin"

  cat > "$base/fakebin/coordinator-handoff-archive.sh" <<'FAKE'
#!/usr/bin/env bash
# Fake stand-in for coordinator-handoff-archive.sh: logs its args and exits 0.
echo "$*" >> "$(dirname "${BASH_SOURCE[0]}")/../stamp-calls.log"
exit 0
FAKE
  chmod +x "$base/fakebin/coordinator-handoff-archive.sh"
}

# ---------------------------------------------------------------------------
# _write_stub PATH KIND ROADMAP_ID STUB_ID DEPLOYMENT_STATE — write a
# minimal origin-stub fixture.
# ---------------------------------------------------------------------------
_write_stub() {
  local path="$1" kind="$2" rid="$3" sid="$4" state="$5"
  cat > "$path" <<EOF
---
title: "fixture stub"
kind: ${kind}
roadmap_id: "${rid}"
stub_id: "${sid}"
deployment_state: ${state}
---

# fixture stub body
EOF
}

# ---------------------------------------------------------------------------
# _write_plan PATH ROADMAP_ID STUB_ID — write a minimal governing-plan
# fixture. ROADMAP_ID/STUB_ID may be "" to omit the field entirely.
# ---------------------------------------------------------------------------
_write_plan() {
  local path="$1" rid="$2" sid="$3"
  {
    echo "---"
    echo "title: fixture plan"
    [[ -n "$rid" ]] && echo "roadmap_id: \"${rid}\""
    [[ -n "$sid" ]] && echo "stub_id: \"${sid}\""
    echo "---"
    echo
    echo "# fixture plan body"
  } > "$path"
}

# _run_subject BASEDIR ARGS... — run the subject inside BASEDIR with the
# fake coordinator-handoff-archive.sh shadowing the real one via a symlink
# placed alongside the subject's own directory resolution (SCRIPT_DIR-relative
# call site), so the subject's own `"${SCRIPT_DIR}/coordinator-handoff-archive.sh"`
# path resolves to the fake. We do this by copying the subject into a scratch
# bin dir next to the fake, so $(dirname "$0") for the SUBJECT resolves to the
# fixture's fakebin.
_run_subject() {
  local base="$1"; shift
  RC=0
  OUT=$(cd "$base" && bash "$base/fakebin/close-origin-stub-on-ship.sh" "$@" 2>"$TMPBASE/stderr") || RC=$?
  ERR=$(cat "$TMPBASE/stderr" 2>/dev/null || true)
}

_install_subject_shim() {
  local base="$1"
  cp "$SUBJECT" "$base/fakebin/close-origin-stub-on-ship.sh"
  chmod +x "$base/fakebin/close-origin-stub-on-ship.sh"
}

RC=0
OUT=""
ERR=""

# ---------------------------------------------------------------------------
# T1 — matching ready_to_fire stub is selected and the stamp is invoked on
# the right path.
# ---------------------------------------------------------------------------
T1="$TMPBASE/t1"
_make_fixture "$T1"
_install_subject_shim "$T1"
_write_stub "$T1/state/handoffs/2026-07-08_1_roadmap-t1-01.md" "spinoff-roadmap" "rm-t1" "t1-01" "ready_to_fire"
_write_plan "$T1/plan.md" "rm-t1" "t1-01"

_run_subject "$T1" --plan "plan.md"

if [[ "$RC" -eq 0 ]]; then
  _pass "T1: exit 0"
else
  _fail "T1: exit 0" "rc=$RC out='$OUT' err='$ERR'"
fi

if [[ -f "$T1/stamp-calls.log" ]] && grep -q "state/handoffs/2026-07-08_1_roadmap-t1-01.md" "$T1/stamp-calls.log" \
   && grep -q -- "--stamp-only" "$T1/stamp-calls.log"; then
  _pass "T1: stamp invoked on the matching stub path with --stamp-only"
else
  _fail "T1: stamp invoked on the matching stub path with --stamp-only" "log content: $(cat "$T1/stamp-calls.log" 2>/dev/null || echo '<missing>')"
fi

if printf '%s\n' "$OUT" | grep -q "closed origin stub"; then
  _pass "T1: success message printed"
else
  _fail "T1: success message printed" "out='$OUT'"
fi

# ---------------------------------------------------------------------------
# T2 — plan with no stub_id (or roadmap_id) is a no-op, exit 0.
# ---------------------------------------------------------------------------
T2="$TMPBASE/t2"
_make_fixture "$T2"
_install_subject_shim "$T2"
_write_plan "$T2/plan.md" "rm-t2" ""   # roadmap_id present, stub_id absent → incomplete pair

_run_subject "$T2" --plan "plan.md"

if [[ "$RC" -eq 0 ]] && printf '%s\n' "$OUT" | grep -q "no (roadmap_id,stub_id) in inputs — no-op"; then
  _pass "T2: no-op message + exit 0 when stub_id is absent"
else
  _fail "T2: no-op message + exit 0 when stub_id is absent" "rc=$RC out='$OUT' err='$ERR'"
fi

if [[ ! -f "$T2/stamp-calls.log" ]]; then
  _pass "T2: stamp never invoked"
else
  _fail "T2: stamp never invoked" "unexpected log: $(cat "$T2/stamp-calls.log")"
fi

# ---------------------------------------------------------------------------
# T3 — stub already deployment_state:shipped is NOT selected (excluded from
# the non-terminal filter, no stamp).
# ---------------------------------------------------------------------------
T3="$TMPBASE/t3"
_make_fixture "$T3"
_install_subject_shim "$T3"
_write_stub "$T3/state/handoffs/2026-07-08_1_roadmap-t3-01.md" "spinoff-roadmap" "rm-t3" "t3-01" "shipped"
_write_plan "$T3/plan.md" "rm-t3" "t3-01"

_run_subject "$T3" --plan "plan.md"

if [[ "$RC" -eq 0 ]] && printf '%s\n' "$OUT" | grep -q "nothing to close"; then
  _pass "T3: already-shipped stub reported as nothing-to-close"
else
  _fail "T3: already-shipped stub reported as nothing-to-close" "rc=$RC out='$OUT' err='$ERR'"
fi

if [[ ! -f "$T3/stamp-calls.log" ]]; then
  _pass "T3: stamp never invoked on an already-shipped stub"
else
  _fail "T3: stamp never invoked on an already-shipped stub" "unexpected log: $(cat "$T3/stamp-calls.log")"
fi

# ---------------------------------------------------------------------------
# T4 — an in_flight stub with matching (rid,sid) is NOT selected — that's
# Step 2.7's job (the consumed predecessor), not this script's.
# ---------------------------------------------------------------------------
T4="$TMPBASE/t4"
_make_fixture "$T4"
_install_subject_shim "$T4"
_write_stub "$T4/state/handoffs/2026-07-08_1_roadmap-t4-01.md" "spinoff-roadmap" "rm-t4" "t4-01" "in_flight"
_write_plan "$T4/plan.md" "rm-t4" "t4-01"

_run_subject "$T4" --plan "plan.md"

if [[ "$RC" -eq 0 ]] && printf '%s\n' "$OUT" | grep -q "nothing to close"; then
  _pass "T4: in_flight stub reported as nothing-to-close (not this script's job)"
else
  _fail "T4: in_flight stub reported as nothing-to-close (not this script's job)" "rc=$RC out='$OUT' err='$ERR'"
fi

if [[ ! -f "$T4/stamp-calls.log" ]]; then
  _pass "T4: stamp never invoked on an in_flight stub"
else
  _fail "T4: stamp never invoked on an in_flight stub" "unexpected log: $(cat "$T4/stamp-calls.log")"
fi

# ---------------------------------------------------------------------------
# T5 — two stubs sharing the same (rid,sid) → ambiguity warning, no stamp.
# ---------------------------------------------------------------------------
T5="$TMPBASE/t5"
_make_fixture "$T5"
_install_subject_shim "$T5"
_write_stub "$T5/state/handoffs/2026-07-08_1_roadmap-t5-01.md" "spinoff-roadmap" "rm-t5" "t5-01" "ready_to_fire"
_write_stub "$T5/state/handoffs/2026-07-08_2_roadmap-t5-01-dup.md" "spinoff" "rm-t5" "t5-01" "awaiting_gate"
_write_plan "$T5/plan.md" "rm-t5" "t5-01"

_run_subject "$T5" --plan "plan.md"

if [[ "$RC" -eq 0 ]]; then
  _pass "T5: exit 0 even on ambiguity (surfaced, non-fatal)"
else
  _fail "T5: exit 0 even on ambiguity (surfaced, non-fatal)" "rc=$RC out='$OUT' err='$ERR'"
fi

if printf '%s\n' "$ERR" | grep -q "WARNING ambiguous"; then
  _pass "T5: ambiguity warning printed to stderr"
else
  _fail "T5: ambiguity warning printed to stderr" "err='$ERR'"
fi

if [[ ! -f "$T5/stamp-calls.log" ]]; then
  _pass "T5: stamp never invoked when ambiguous"
else
  _fail "T5: stamp never invoked when ambiguous" "unexpected log: $(cat "$T5/stamp-calls.log")"
fi

# ---------------------------------------------------------------------------
# T6 — regression guard for comment-strip-before-quote-strip (Finding 1):
#   (a) a quoted stub_id containing "#" (e.g. "idx-01#c3") must be extracted
#       IN FULL and joined correctly — pre-fix, the comment-strip truncated
#       this to "idx-01" before the quote-strip ever ran.
#   (b) an unquoted value with a legitimate trailing " # comment" must still
#       have the comment stripped correctly (regression guard that the fix
#       didn't break legitimate comment-stripping).
# ---------------------------------------------------------------------------
T6="$TMPBASE/t6"
_make_fixture "$T6"
_install_subject_shim "$T6"

# (a) quoted stub_id containing "#"
cat > "$T6/state/handoffs/2026-07-08_1_roadmap-t6-01.md" <<'EOF'
---
title: "fixture stub"
kind: spinoff-roadmap
roadmap_id: "rm-t6"
stub_id: "idx-01#c3"
deployment_state: ready_to_fire
---

# fixture stub body
EOF
cat > "$T6/plan.md" <<'EOF'
---
title: fixture plan
roadmap_id: "rm-t6"
stub_id: "idx-01#c3"
---

# fixture plan body
EOF

_run_subject "$T6" --plan "plan.md"

if [[ -f "$T6/stamp-calls.log" ]] && grep -q "state/handoffs/2026-07-08_1_roadmap-t6-01.md" "$T6/stamp-calls.log"; then
  _pass "T6a: quoted stub_id containing '#' extracted in full and joined correctly"
else
  _fail "T6a: quoted stub_id containing '#' extracted in full and joined correctly" "rc=$RC out='$OUT' err='$ERR' log='$(cat "$T6/stamp-calls.log" 2>/dev/null || echo '<missing>')'"
fi

if printf '%s\n' "$OUT" | grep -q "idx-01#c3"; then
  _pass "T6a: output names the FULL stub_id (idx-01#c3), not a truncated prefix"
else
  _fail "T6a: output names the FULL stub_id (idx-01#c3), not a truncated prefix" "out='$OUT'"
fi

# (b) unquoted value with a legitimate trailing comment — still a distinct
# stub/plan pair so it doesn't collide with (a)'s join above.
T6b="$TMPBASE/t6b"
_make_fixture "$T6b"
_install_subject_shim "$T6b"
cat > "$T6b/state/handoffs/2026-07-08_1_roadmap-t6b-01.md" <<'EOF'
---
title: "fixture stub"
kind: spinoff-roadmap
roadmap_id: rm-t6b  # FK to roadmap
stub_id: t6b-01
deployment_state: ready_to_fire
---

# fixture stub body
EOF
cat > "$T6b/plan.md" <<'EOF'
---
title: fixture plan
roadmap_id: rm-t6b  # FK to roadmap
stub_id: t6b-01
---

# fixture plan body
EOF

_run_subject "$T6b" --plan "plan.md"

if [[ -f "$T6b/stamp-calls.log" ]] && grep -q "state/handoffs/2026-07-08_1_roadmap-t6b-01.md" "$T6b/stamp-calls.log"; then
  _pass "T6b: unquoted value with legitimate trailing comment still stripped and joined correctly"
else
  _fail "T6b: unquoted value with legitimate trailing comment still stripped and joined correctly" "rc=$RC out='$OUT' err='$ERR' log='$(cat "$T6b/stamp-calls.log" 2>/dev/null || echo '<missing>')'"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo "PASS=${PASS} FAIL=${FAIL}"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
