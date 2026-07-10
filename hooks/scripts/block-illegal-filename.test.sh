#!/usr/bin/env bash
# block-illegal-filename.test.sh — test suite for block-illegal-filename.sh PreToolUse hook.
#
# Purpose: exercises the reliable arm (Write/Edit/NotebookEdit file_path extraction) and
# a representative literal Bash arm case. Does NOT assert Bash-arm exhaustiveness
# (variable/heredoc patterns are explicitly best-effort — the commit/merge backstop is
# the real net for Bash-constructed paths).
#
# Per the Staff Engineer review F4: test the reliable arm + representative literal Bash case only.
#
# Test vectors:
#   (a) Write with a colon-named file_path → BLOCKED (reliable arm)
#   (b) Write with a safe file_path → ALLOWED (reliable arm)
#   (c) Literal `mv a b:c` Bash command → ADVISORY (best-effort arm, non-blocking)
#   (d) Override env var COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1 → ALLOWED
#   (i) Redirect to colon-named file outside heredoc → ADVISORY (best-effort arm, non-blocking)
#   (i2) mv to trailing-dot file outside heredoc → ADVISORY (best-effort arm, non-blocking)
#   (j) Double-quoted --body with angle-bracket template tokens → ALLOWED
#   (j2) Single-quoted --body with angle-bracket template tokens → ALLOWED
#   (k) Multi-line git commit -m body with '->' prose arrow → ALLOWED
#   (k2) Multi-line git commit -m body with '=>' and 'a|b' prose → ALLOWED
#   (k3) Multi-line compound: git commit + redirect to illegal file → ADVISORY (best-effort arm, non-blocking)
#   (m) bash &>file combined redirect with illegal name → ALLOWED (v1 limitation)
#   (n) Multi-line -m body with ' > doc:note.md' line → ALLOWED (Change B isolation)
#   (o) --out with quoted var + 2>&1 redirect → ALLOWED, no advisory (Change 2 --out fix)
#   (p) F6: heredoc/process-substitution tokens glued onto a redirect target
#       (`cat >file<<EOF`, `<<-`, `<<<`, `<(`) → ALLOWED, no advisory
#   (p2) F6 regression floor: a GENUINE illegal `<` in a literal filename
#        (`foo<bar`) still produces an advisory
#
# Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § D1, AC5
# Tripwire: docs/wiki/coordinator-tripwires.md § BLOCK-ILLEGAL-FILENAME

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/block-illegal-filename.sh"

[[ -f "$HOOK" ]] || { echo "FAIL: hook not found at $HOOK"; exit 1; }
[[ -x "$HOOK" ]] || chmod +x "$HOOK"

# ---------------------------------------------------------------------------
# Minimal harness
# ---------------------------------------------------------------------------
PASS=0
FAIL=0
SKIP=0
FAIL_NAMES=()

pass() {
  printf 'PASS: %s\n' "$1"
  PASS=$((PASS + 1))
}

fail() {
  local label="$1" detail="${2:-}"
  printf 'FAIL: %s%s\n' "$label" "${detail:+ — $detail}"
  FAIL=$((FAIL + 1))
  FAIL_NAMES+=("$label")
}

# ---------------------------------------------------------------------------
# JSON payload builders (portable: python3 → python → manual escape)
# ---------------------------------------------------------------------------
_PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

make_write_payload() {
  local tool="$1" path="$2"
  if [[ -n "$_PY" ]]; then
    # Review: code-reviewer F9/F10 — pipe path via stdin to avoid two Windows pitfalls:
    # (a) Shell-expanding into a Python literal makes ' or \ produce invalid Python.
    # (b) MSYS2/Git-Bash converts POSIX-looking argv paths (e.g. /repo/foo\bar.md →
    #     C:/Program Files/Git/repo/foo/bar.md), destroying the literal '\'.
    # Stdin pipe bytes are NOT subject to MSYS2 path conversion.
    # Tool name ("Write"/"Edit") has no path chars → safe as a CSN_TOOL env var.
    printf '%s' "$path" | CSN_TOOL="$tool" "$_PY" -c '
import json, sys, os
path = sys.stdin.read()
tool = os.environ["CSN_TOOL"]
print(json.dumps({"tool_name": tool, "tool_input": {"file_path": path}}))
'
  else
    local ep="${path//\\/\\\\}"; ep="${ep//\"/\\\"}"
    printf '{"tool_name":"%s","tool_input":{"file_path":"%s"}}' "$tool" "$ep"
  fi
}

make_bash_payload() {
  local cmd="$1"
  if [[ -n "$_PY" ]]; then
    printf '%s' "$cmd" | "$_PY" -c '
import json, sys
cmd = sys.stdin.read()
print(json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))
'
  else
    local esc="${cmd//\\/\\\\}"; esc="${esc//\"/\\\"}"
    printf '{"tool_name":"Bash","tool_input":{"command":"%s"}}' "$esc"
  fi
}

# Run the hook and return its output and exit code.
run_hook() {
  local payload="$1"
  local env_extra="${2:-}"
  if [[ -n "$env_extra" ]]; then
    OUTPUT=$(env "$env_extra" bash "$HOOK" <<< "$payload" 2>/dev/null)
  else
    OUTPUT=$(bash "$HOOK" <<< "$payload" 2>/dev/null)
  fi
  EXIT_CODE=$?
  printf '%s' "$OUTPUT"
}

is_denied() {
  local output="$1"
  printf '%s' "$output" | grep -q '"deny"'
}

is_advisory() {
  local output="$1"
  printf '%s' "$output" | grep -q 'ILLEGAL-FILENAME ADVISORY'
}

# ---------------------------------------------------------------------------
# (a) Write with a colon-named file_path → BLOCKED (reliable arm)
# ---------------------------------------------------------------------------
LABEL="(a) Write colon-named file_path blocked (reliable arm)"
PAYLOAD=$(make_write_payload "Write" "/home/user/state/handoffs/2026-06-30T12:00:00Z-foo.md")
OUT=$(run_hook "$PAYLOAD")
if is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected deny, got: $(printf '%s' "$OUT" | head -c 200)"
fi

# Also test Edit tool — same reliable arm.
LABEL="(a2) Edit colon-named file_path blocked (reliable arm)"
PAYLOAD=$(make_write_payload "Edit" "/repo/tasks/my:file.md")
OUT=$(run_hook "$PAYLOAD")
if is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected deny, got: $(printf '%s' "$OUT" | head -c 200)"
fi

# Other illegal chars: ? * < > " |
# Note: '\' is intentionally omitted from this loop. The Windows-backslash fix
# (##*[/\\]) consumes '\' as a path separator during leaf extraction, so a POSIX
# path like /repo/foo\bar.md now yields leaf "bar.md" (legal) rather than
# "foo\bar.md" (illegal). A literal '\' inside a POSIX leaf is itself NTFS-illegal
# and vanishingly rare; the commit/merge backstop (check-no-illegal-paths.sh) is
# the net for that edge case. See (f1)/(f2) below for the Windows-path regression.
# Review: code-reviewer F10 — added | (after F9 payload fix, paths with these chars are now safe to pass)
for _char in '?' '*' '<' '>' '"' '|'; do
  LABEL="(a3) Write with '${_char}' in basename blocked"
  PAYLOAD=$(make_write_payload "Write" "/repo/foo${_char}bar.md")
  OUT=$(run_hook "$PAYLOAD")
  if is_denied "$OUT"; then
    pass "$LABEL"
  else
    fail "$LABEL" "expected deny, got: $(printf '%s' "$OUT" | head -c 200)"
  fi
done

# Trailing dot — illegal on NTFS
LABEL="(a4) Write with trailing dot in basename blocked"
PAYLOAD=$(make_write_payload "Write" "/repo/foo.")
OUT=$(run_hook "$PAYLOAD")
if is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected deny, got: $(printf '%s' "$OUT" | head -c 200)"
fi

# Trailing space — illegal on NTFS
LABEL="(a5) Write with trailing space in basename blocked"
PAYLOAD=$(make_write_payload "Write" "/repo/foo ")
OUT=$(run_hook "$PAYLOAD")
if is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected deny, got: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (b) Write with a safe file_path → ALLOWED (reliable arm)
# ---------------------------------------------------------------------------
LABEL="(b) Write with safe file_path allowed"
PAYLOAD=$(make_write_payload "Write" "/home/user/state/handoffs/2026-06-30T12-00-00Z-foo.md")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow, got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

LABEL="(b2) Write with normal basename allowed"
PAYLOAD=$(make_write_payload "Write" "/repo/docs/wiki/cross-platform-shell-portability.md")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow, got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (c) Literal `mv a b:c` Bash command → ADVISORY (best-effort arm, non-blocking)
# ---------------------------------------------------------------------------
LABEL="(c) Literal mv a b:c bash command advisory (best-effort arm, non-blocking)"
PAYLOAD=$(make_bash_payload "mv state/handoffs/old.md state/handoffs/2026-06-30T12:00:00Z-new.md")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected advisory (not denied), got: $(printf '%s' "$OUT" | head -c 200)"
fi

# Also test git mv form
LABEL="(c2) Literal git mv a b:c bash command advisory (best-effort arm, non-blocking)"
PAYLOAD=$(make_bash_payload "git mv old.md foo:bar.md")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected advisory (not denied), got: $(printf '%s' "$OUT" | head -c 200)"
fi

# Safe mv should be allowed
LABEL="(c3) Literal mv with safe dest allowed"
PAYLOAD=$(make_bash_payload "mv old.md new-name-2026-06-30T12-00-00Z.md")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow, got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (d) Override env var COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1 → ALLOWED
# ---------------------------------------------------------------------------
LABEL="(d) Override env var bypasses colon-named Write"
PAYLOAD=$(make_write_payload "Write" "/repo/foo:bar.md")
OUT=$(COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1 bash "$HOOK" <<< "$PAYLOAD" 2>/dev/null)
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow with override, got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

LABEL="(d2) Override env var bypasses mv colon Bash command"
PAYLOAD=$(make_bash_payload "mv a b:c")
OUT=$(COORDINATOR_OVERRIDE_ILLEGAL_FILENAME=1 bash "$HOOK" <<< "$PAYLOAD" 2>/dev/null)
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow with override, got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (f) Windows backslash-separated paths — leaf extraction regression
#     Pre-fix: ${FILE_PATH##*/} found no '/' and returned the entire path as
#     the leaf; csn_check then flagged the drive-letter colon (X:) and falsely
#     denied a path whose actual leaf was legal.
#     Post-fix: ${FILE_PATH##*[/\\]} strips up to the last '/' OR '\', yielding
#     the true leaf on both POSIX and Windows paths.
# ---------------------------------------------------------------------------

# (f1) Windows absolute path with a clean leaf must be ALLOWED.
# Reproduced memo symptom: X:\repo\state\memo-outbox\topic.md denied on X: colon.
LABEL="(f1) Write with Windows backslash path + clean leaf allowed"
PAYLOAD=$(make_write_payload "Write" 'X:\repo\state\memo-outbox\topic.md')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow (leaf=topic.md is legal), got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# (f2) Windows absolute path with an ILLEGAL leaf must still be DENIED.
# Proves the leaf is extracted correctly (not that we stopped checking).
LABEL="(f2) Write with Windows backslash path + illegal leaf (?) denied"
PAYLOAD=$(make_write_payload "Write" 'X:\repo\foo?bar.md')
OUT=$(run_hook "$PAYLOAD")
if is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected deny (leaf=foo?bar.md has illegal '?'), got allow: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (g) CONTENT IS NOT SCANNED — colon/pipe in new_string with a clean file_path
#     must be ALLOWED. Pins the invariant that the hook guards the file_path
#     LEAF only, never the Edit/Write payload. A 2026-06-30 bug-backlog entry
#     ("illegal-path guard false-positives on legitimate Edit/Write CONTENT")
#     misdiagnosed the drive-letter-colon false-positive (f1) as content
#     scanning: both reported edits targeted Windows C:\ paths and tripped the
#     X: colon regardless of payload — the colon/pipe in the prose (yaml
#     key:value, regex a|b) was coincidental. No surface scans content; this
#     case fails loudly if one is ever introduced.
# ---------------------------------------------------------------------------
LABEL="(g) Edit with colon+pipe in new_string but clean file_path allowed"
if [[ -n "$_PY" ]]; then
  PAYLOAD=$(CSN_PATH='C:\Users\u\.claude\docs\plans\reviewer-findings-self-persist.md' "$_PY" -c '
import json, os
print(json.dumps({"tool_name": "Edit", "tool_input": {
    "file_path": os.environ["CSN_PATH"],
    "old_string": "x",
    "new_string": "access-mode: read-write\nEdit|Write|MultiEdit"}}))
')
  OUT=$(run_hook "$PAYLOAD")
  if ! is_denied "$OUT"; then
    pass "$LABEL"
  else
    fail "$LABEL" "expected allow (content is never scanned), got deny: $(printf '%s' "$OUT" | head -c 200)"
  fi
else
  printf 'SKIP: %s (no python for payload build)\n' "$LABEL"
  SKIP=$((SKIP + 1))
fi

# ---------------------------------------------------------------------------
# (h) Bash heredoc body is NOT scanned — content with > and trailing-dot
#     token inside a Python heredoc must be ALLOWED.
#     Regression for the false-positive where heredoc body was scanned as
#     shell tokens, causing python3 - <<'PY'\n...\nPY commands to be blocked.
# ---------------------------------------------------------------------------
LABEL="(h) Python heredoc body with > and trailing-dot token is allowed"
# Build a command: python3 - <<'PY' ... PY  where the body contains a '>'
# operator and a backtick-dot token. Neither should be scanned as mv/redirect.
_HERED_CMD=$(printf 'python3 - <<'"'"'PY'"'"'\n# os.replace(tmp, out_path)\nx = `%s`\nPY\ngit commit -m msg' '.')
PAYLOAD=$(make_bash_payload "$_HERED_CMD")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow (heredoc body must not be scanned as shell tokens), got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (i) Genuine illegal redirect/mv outside any heredoc → ADVISORY (best-effort arm, non-blocking).
#     The Bash arm now emits a non-blocking advisory instead of blocking; the
#     commit/merge backstop (check-no-illegal-paths.sh) is the real enforcement net.
# ---------------------------------------------------------------------------
LABEL="(i) Redirect to colon-named file outside heredoc is advisory (best-effort arm, non-blocking)"
PAYLOAD=$(make_bash_payload "echo x > some:illegal.md")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected advisory (not denied), got: $(printf '%s' "$OUT" | head -c 200)"
fi

LABEL="(i2) mv to trailing-dot file outside heredoc is advisory (best-effort arm, non-blocking)"
PAYLOAD=$(make_bash_payload "mv a.txt b.md.")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected advisory (not denied), got: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (j) Double-quoted --body value with angle-bracket template tokens must be ALLOWED.
#     Regression for false-positive where a closing '>' inside a quoted --body span
#     was misread as a shell redirect operator, causing the following token to be
#     extracted and flagged for an NTFS-illegal '<'.
# ---------------------------------------------------------------------------
LABEL="(j) coordinator-lesson-add with double-quoted --body containing angle-bracket tokens allowed"
PAYLOAD=$(make_bash_payload 'coordinator-lesson-add --body "use grep -riE <PATTERN> <PATHS> to find it"')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow (angle-brackets inside double-quoted --body must not be scanned as redirect), got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# (j2) Same as (j) but with single-quoted --body value.
LABEL="(j2) coordinator-lesson-add with single-quoted --body containing angle-bracket tokens allowed"
PAYLOAD=$(make_bash_payload "coordinator-lesson-add --body 'use grep -riE <PATTERN> <PATHS> to find it'")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow (angle-brackets inside single-quoted --body must not be scanned as redirect), got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (k) Multi-line git commit -m body with '->' in prose — MUST BE ALLOWED.
#     Regression: best-effort arm's redirect extractor previously matched '>'
#     from '->' inside commit message bodies that survived the line-by-line sed
#     quoted-span strip (sed is line-oriented; a multi-line -m "..." body has no
#     closing '"' on its opening line, so the span is never stripped).
#     Fix: redirect extraction now anchored to shell-token boundaries so '->'
#     (no whitespace before '>') never matches as a shell redirect operator.
#     Spec: cross-repo/inbox/2026-07-01-block-illegal-filename-commit-message-false-positive.md
# ---------------------------------------------------------------------------
LABEL="(k) git commit -m multi-line body with '->' prose arrow allowed"
# Construct a command with actual newlines (ANSI-C $'...' quoting).
# Body: "widened [19,34]->[19,35])." — the '->[19,35]).' previously triggered
# a trailing-dot false-deny via the redirect extractor.
_MULTILINE_COMMIT=$'git commit -q -m "chore(handoff): consume memo\n\naddon memo actioned+accepted (widened [19,34]->[19,35]). Regenerated tracker.\n..."'
PAYLOAD=$(make_bash_payload "$_MULTILINE_COMMIT")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow (multi-line commit body '->' is not a redirect), got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# (k2) Multi-line git commit -m body containing '=>' and 'a|b' — MUST BE ALLOWED.
#      Regression guard: '=>' is a prose arrow (TypeScript, C++, range notation),
#      not a shell redirect. 'a|b' is regex alternation, not a pipe. Neither should
#      trigger the redirect scanner when embedded in a multi-line commit message body.
LABEL="(k2) git commit -m multi-line body with '=>' and 'a|b' prose allowed"
_MULTILINE_COMMIT2=$'git commit -q -m "fix(types): narrow result type\n\nPattern changed from a=>b and regex a|b to stricter form.\n..."'
PAYLOAD=$(make_bash_payload "$_MULTILINE_COMMIT2")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow ('=>' and 'a|b' in commit body are not redirects), got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# (k3) Multi-line compound: git commit message + genuine redirect to illegal file.
#      The Bash arm now emits a non-blocking advisory instead of blocking.
#      The commit body `"cleanup memo"` is stripped; the echo redirect on the next
#      line is detected by the scanner and produces an advisory. The commit/merge
#      backstop (check-no-illegal-paths.sh) is the real enforcement net.
LABEL="(k3) multi-line compound: commit followed by redirect to illegal file advisory (best-effort arm, non-blocking)"
_COMPOUND_CMD=$'git commit -m "cleanup memo"\necho x > real:illegal.md'
PAYLOAD=$(make_bash_payload "$_COMPOUND_CMD")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected advisory (not denied), got: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (o) Regression: --out with quoted variable + 2>&1 redirect (the memo bug).
#     Before fix: quote-strip left `--out  2>&1`, so the scanner read `2>&1` as the
#     --out value and flagged `>`. After fix: --out is extracted from original $CMD,
#     captures "$SPINOFF_FILE" (a $var), which check_candidate skips. 2>&1 is never
#     read as a path. Expect: NOT denied AND no advisory.
# ---------------------------------------------------------------------------
LABEL="(o) --out with quoted var + 2>&1 not denied and no advisory (Change 2 --out fix)"
_CMD_O='bash "/usr/local/bin/coordinator-doc-new" --type spinoff --title "x" --out "$SPINOFF_FILE" 2>&1 | tail -5'
PAYLOAD=$(make_bash_payload "$_CMD_O")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && ! is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow + no advisory (2>&1 must not be read as --out value), got: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (m) `&>file` combined redirect — ACCEPTED v1 LIMITATION (NOT desired behavior).
#     `&` is not in the token-boundary anchor (^|[[:space:]]|[0-9]) so
#     `&>file:illegal.md` passes undetected. This test documents the gap.
#     The commit/merge backstop (check-no-illegal-paths.sh) is the real net.
#     (Review: F1 — &>file over-allow documented as accepted gap)
# ---------------------------------------------------------------------------
LABEL="(m) bash &>file:illegal.md is currently ALLOWED (accepted v1 limitation — NOT desired)"
PAYLOAD=$(make_bash_payload "bash script.sh &>log:file.md")
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow (v1 limitation: & not a token-boundary anchor), got deny: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# (n) Change B isolation — perl slurp prevents false-positive on a multi-line
#     -m body containing ' > doc:note.md' on its own line.
#     Change A's token-boundary regex WOULD match ' > doc:note.md' (space before
#     '>') if it survived to the redirect scanner. Change B (perl -0777 slurp)
#     strips the entire multi-line "..." body including that line — so the
#     redirect scanner never sees it → ALLOW.
#     This test FAILS if Change B is silently broken while Change A still passes.
#     Skipped when perl is absent (perl-absent residual documented in n2 below).
#     (Review: F2 — Change B isolation test)
# ---------------------------------------------------------------------------
LABEL="(n) multi-line -m body with ' > doc:note.md' line allowed (Change B perl-slurp isolation)"
if command -v perl >/dev/null 2>&1; then
  _MULTILINE_BODY_REDIR=$'git commit -m "update tracking\n\n > doc:note.md is the new output path"\necho done'
  PAYLOAD=$(make_bash_payload "$_MULTILINE_BODY_REDIR")
  OUT=$(run_hook "$PAYLOAD")
  if ! is_denied "$OUT"; then
    pass "$LABEL"
  else
    fail "$LABEL" "expected allow (perl slurp strips multi-line -m body), got deny: $(printf '%s' "$OUT" | head -c 200)"
  fi
else
  printf 'SKIP: %s (perl absent — Change B requires perl; see n2 note)\n' "$LABEL"
  SKIP=$((SKIP + 1))
fi

# (n2) perl-bypass residual — documented here, no live test.
#      When perl is absent (or broken — see F3 fall-through fix), the sed fallback
#      is line-oriented. A multi-line -m "..." body is NOT fully stripped: the
#      ' > doc:note.md' line survives to the redirect scanner and produces a BLOCK
#      (false-positive deny). This is an accepted v1 limitation. The commit/merge
#      backstop (check-no-illegal-paths.sh) is the real enforcement net.
#      Live test omitted: PATH surgery to force perl-absence is brittle across
#      environments. See sidecar F2 and block-illegal-filename.sh v1 LIMITATIONS.

# ---------------------------------------------------------------------------
# (p) F6 regression: heredoc / process-substitution tokens glued onto a
#     redirect target (no whitespace before the operator) must NOT be
#     misread as a genuine '<' in a filename.
#     Root cause: `cat >file<<EOF` tokenizes under the redirect-capture regex
#     as destination "file<<EOF"; csn_check then flagged the harmless '<' from
#     the heredoc marker as NTFS-illegal. Fix strips a trailing <<, <<-, <<<,
#     or <( token from the candidate before running csn_check.
#     Spec backlink: tasks/2026-07-08-install-dogfood-friction.md § F6
# ---------------------------------------------------------------------------
LABEL="(p) cat >file<<EOF (no space, heredoc) allowed, no advisory"
PAYLOAD=$(make_bash_payload 'cat >file<<EOF')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && ! is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow + no advisory, got: $(printf '%s' "$OUT" | head -c 200)"
fi

LABEL="(p1b) cat >file<<EOF with heredoc body (real newlines) allowed, no advisory"
PAYLOAD=$(make_bash_payload $'cat >file<<EOF\nbody\nEOF')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && ! is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow + no advisory, got: $(printf '%s' "$OUT" | head -c 200)"
fi

LABEL="(p1c) cat >/tmp/f<<- tab-strip heredoc form allowed, no advisory"
PAYLOAD=$(make_bash_payload $'cat > /tmp/f <<-EOF\n\tbody\n\tEOF')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && ! is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow + no advisory, got: $(printf '%s' "$OUT" | head -c 200)"
fi

LABEL="(p1d) here-string <<< allowed, no advisory"
PAYLOAD=$(make_bash_payload 'grep foo <<< "hello:world"')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && ! is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow + no advisory, got: $(printf '%s' "$OUT" | head -c 200)"
fi

LABEL="(p1e) process substitution diff <(a) <(b) allowed, no advisory"
PAYLOAD=$(make_bash_payload 'diff <(cat a) <(cat b)')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && ! is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow + no advisory, got: $(printf '%s' "$OUT" | head -c 200)"
fi

# (p2) Regression floor: a GENUINE illegal '<' in a literal filename (no
#      heredoc/process-sub involved) must still produce an advisory.
LABEL="(p2) echo x > foo<bar (genuine illegal '<') still advisory"
PAYLOAD=$(make_bash_payload 'echo x > foo<bar')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected advisory (not denied), got: $(printf '%s' "$OUT" | head -c 200)"
fi

LABEL="(p2b) mv a foo<bar (genuine illegal '<' via mv) still advisory"
PAYLOAD=$(make_bash_payload 'mv a foo<bar')
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT" && is_advisory "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected advisory (not denied), got: $(printf '%s' "$OUT" | head -c 200)"
fi

# ---------------------------------------------------------------------------
# Additional: Non-Bash/Write/Edit/NotebookEdit tool_names are silently ignored
# ---------------------------------------------------------------------------
LABEL="(e) Unknown tool_name (Read) is silently allowed"
PAYLOAD='{"tool_name":"Read","tool_input":{"file_path":"/repo/foo:bar.md"}}'
OUT=$(run_hook "$PAYLOAD")
if ! is_denied "$OUT"; then
  pass "$LABEL"
else
  fail "$LABEL" "expected allow for Read tool, got deny"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((PASS + FAIL))
if [[ "$SKIP" -gt 0 ]]; then
  printf '\n%d/%d tests passed, %d skipped\n' "$PASS" "$TOTAL" "$SKIP"
else
  printf '\n%d/%d tests passed\n' "$PASS" "$TOTAL"
fi

if [[ "$FAIL" -gt 0 ]]; then
  printf 'Failed tests:\n'
  for name in "${FAIL_NAMES[@]}"; do
    printf '  - %s\n' "$name"
  done
  exit 1
fi

exit 0
