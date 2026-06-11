#!/usr/bin/env bash
# bin/coordinator-setup-state.test.sh — behavior tests for the setup-state receipt primitive.
#
# Covers: seed-on-first-record, idempotent first-occurrence-wins, check exit codes,
# status absence/presence, and bad-arg rejection. Uses a throwaway CLAUDE_HOME.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUT="$SCRIPT_DIR/coordinator-setup-state.sh"

PASS=0
FAIL=0
ok()   { echo "  ok: $1"; PASS=$((PASS + 1)); }
bad()  { echo "FAIL: $1"; FAIL=$((FAIL + 1)); }

TMPHOME="$(mktemp -d)"
trap 'rm -rf "$TMPHOME"' EXIT
export CLAUDE_HOME="$TMPHOME"
STATE="$TMPHOME/coordinator-setup-state.yaml"

# 1. No receipt yet → check fails, status exits non-zero.
"$SUT" check setup_concluded && bad "check should fail before any record" || ok "check fails pre-record"
"$SUT" status >/dev/null 2>&1 && bad "status should exit non-zero when absent" || ok "status non-zero when absent"

# 2. record seeds the file and the key.
"$SUT" record setup_concluded >/dev/null
[[ -f "$STATE" ]] && ok "receipt file created" || bad "receipt file missing after record"
grep -qE '^version: 1' "$STATE" && ok "version header present" || bad "version header missing"
"$SUT" check setup_concluded && ok "check passes after record" || bad "check should pass after record"

# 3. Idempotent: re-record does not change the timestamp.
FIRST="$(grep '^setup_concluded_at:' "$STATE")"
sleep 1
"$SUT" record setup_concluded >/dev/null
SECOND="$(grep '^setup_concluded_at:' "$STATE")"
[[ "$FIRST" == "$SECOND" ]] && ok "first-occurrence-wins (timestamp unchanged)" || bad "timestamp was overwritten: '$FIRST' -> '$SECOND'"

# 4. Independent milestones coexist.
"$SUT" record orientation_started >/dev/null
"$SUT" check orientation_started && ok "orientation_started recorded" || bad "orientation_started not recorded"
"$SUT" check orientation_completed && bad "orientation_completed should be unset" || ok "orientation_completed still unset"
grep -qE '^setup_concluded_at:' "$STATE" && ok "setup_concluded survived second record" || bad "setup_concluded clobbered"

# 5. Bad milestone / missing arg rejected (exit 2), across subcommands.
"$SUT" record bogus 2>/dev/null; [[ $? -eq 2 ]] && ok "record: bad milestone rejected" || bad "record: bad milestone not rejected"
"$SUT" record 2>/dev/null;       [[ $? -eq 2 ]] && ok "record: missing milestone rejected" || bad "record: missing milestone not rejected"
"$SUT" check bogus 2>/dev/null;  [[ $? -eq 2 ]] && ok "check: bad milestone rejected" || bad "check: bad milestone not rejected"
"$SUT" 2>/dev/null;              [[ $? -eq 2 ]] && ok "missing command rejected" || bad "missing command not rejected"
"$SUT" --help 2>/dev/null;       [[ $? -eq 2 ]] && ok "--help exits via usage (2)" || bad "--help did not exit 2"

# 6. status prints the receipt when present.
"$SUT" status 2>/dev/null | grep -qE '^orientation_started_at:' && ok "status prints receipt" || bad "status did not print receipt"

# 7. Header-only receipt (seeded, no milestone) → status exits non-zero.
HDRHOME="$(mktemp -d)"
printf '# header comment\nversion: 1\n' > "$HDRHOME/coordinator-setup-state.yaml"
CLAUDE_HOME="$HDRHOME" "$SUT" status >/dev/null 2>&1 \
  && bad "status should exit non-zero on header-only file" \
  || ok "status non-zero on header-only file"
rm -rf "$HDRHOME"

# 8. auto-record-if-source-is-live: no registry → no-op, exit 0.
AUTOHOME="$(mktemp -d)"
CLAUDE_HOME="$AUTOHOME" "$SUT" auto-record-if-source-is-live
[[ $? -eq 0 ]] && ok "auto-record: exit 0 when registry absent" || bad "auto-record: nonzero when registry absent"
[[ ! -f "$AUTOHOME/coordinator-setup-state.yaml" ]] && ok "auto-record: no receipt written when registry absent" || bad "auto-record: receipt created without registry"

# 9. auto-record-if-source-is-live: registry without source_is_live → no-op.
mkdir -p "$AUTOHOME/machine-local"
cat > "$AUTOHOME/machine-local/registry.local.toml" <<'EOF'
[plugin.mirrors.coordinator-claude]
propagation_mode = "copy_install"
EOF
CLAUDE_HOME="$AUTOHOME" "$SUT" auto-record-if-source-is-live
[[ ! -f "$AUTOHOME/coordinator-setup-state.yaml" ]] && ok "auto-record: skips copy_install" || bad "auto-record: wrote receipt for copy_install"

# 10. auto-record-if-source-is-live: source_is_live → records setup_concluded silently.
cat > "$AUTOHOME/machine-local/registry.local.toml" <<'EOF'
[plugin.mirrors.coordinator-claude]
propagation_mode = "source_is_live"
EOF
out="$(CLAUDE_HOME="$AUTOHOME" "$SUT" auto-record-if-source-is-live 2>&1)"
[[ -z "$out" ]] && ok "auto-record: silent on source_is_live" || bad "auto-record: produced output: $out"
CLAUDE_HOME="$AUTOHOME" "$SUT" check setup_concluded \
  && ok "auto-record: setup_concluded recorded on source_is_live" \
  || bad "auto-record: setup_concluded not recorded on source_is_live"

# 11. auto-record-if-source-is-live: second call is a no-op (first-write-wins).
FIRST_AUTO="$(grep '^setup_concluded_at:' "$AUTOHOME/coordinator-setup-state.yaml")"
sleep 1
CLAUDE_HOME="$AUTOHOME" "$SUT" auto-record-if-source-is-live
SECOND_AUTO="$(grep '^setup_concluded_at:' "$AUTOHOME/coordinator-setup-state.yaml")"
[[ "$FIRST_AUTO" == "$SECOND_AUTO" ]] && ok "auto-record: idempotent" || bad "auto-record: rewrote timestamp"
rm -rf "$AUTOHOME"

echo "----"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
