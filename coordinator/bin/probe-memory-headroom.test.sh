#!/usr/bin/env bash
# bin/probe-memory-headroom.test.sh — Behavioral coverage for probe-memory-headroom.sh.
#
# Proves the probe's CONTRACT (stable output shape + graceful degradation), not a specific
# machine's numbers: every field is always present, every value is an integer or the literal
# `unknown`, exit is always 0 on success, and --human never crashes. On Linux (/proc/meminfo
# present) it additionally proves ram_available_mb is a real number — the path the fan-out
# memory-pressure signal depends on.
#
# Spec backlink: docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md §111-114 (successor signal).
# set -e so a bug in the harness itself (wrong arity, empty capture fed to a comparison)
# aborts loudly rather than silently logging a false PASS. Assertions use if/else, never
# `[[ ]] && _ok || _bad` (which double-fires _bad if _ok ever returns non-zero).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE="${SCRIPT_DIR}/probe-memory-headroom.sh"

PASS=0
FAIL=0
_ok()  { echo "  PASS: $1"; PASS=$((PASS + 1)); return 0; }
_bad() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL + 1)); return 0; }

_is_int_or_unknown() { [[ "$1" =~ ^[0-9]+$ || "$1" == "unknown" ]]; }
_field() { printf '%s\n' "$1" | awk -F= -v k="$2" '$1==k {print $2; exit}'; }

echo "=== Test A: key=value mode — all four keys present, exit 0 ==="
# `|| RC=$?` captures a non-zero exit without tripping set -e (RC defaults 0 on success).
RC=0; OUT="$(bash "$PROBE" 2>/dev/null)" || RC=$?
if [[ "$RC" -eq 0 ]]; then _ok "A0: exit zero"; else _bad "A0: exit zero" "rc=$RC"; fi
for key in ram_available_mb ram_total_mb vram_free_mb vram_total_mb; do
    if printf '%s\n' "$OUT" | grep -q "^${key}="; then
        _ok "A: key '${key}' present"
    else
        _bad "A: key '${key}' present" "out=$OUT"
    fi
done

echo "=== Test B: every value is an integer or the literal 'unknown' ==="
for key in ram_available_mb ram_total_mb vram_free_mb vram_total_mb; do
    v="$(_field "$OUT" "$key")"
    if _is_int_or_unknown "$v"; then
        _ok "B: ${key}='${v}' is int|unknown"
    else
        _bad "B: ${key} int|unknown" "got='${v}'"
    fi
done

echo "=== Test C: --human mode prints a sentence, exit 0 ==="
RC=0; HOUT="$(bash "$PROBE" --human 2>/dev/null)" || RC=$?
if [[ "$RC" -eq 0 ]]; then _ok "C0: exit zero"; else _bad "C0: exit zero" "rc=$RC"; fi
if [[ "$HOUT" == *"memory headroom"* ]]; then _ok "C1: human line mentions 'memory headroom'"; else _bad "C1: human line" "out=$HOUT"; fi

echo "=== Test D: bad argument → usage error, exit 2 ==="
RC=0; bash "$PROBE" --bogus >/dev/null 2>&1 || RC=$?
if [[ "$RC" -eq 2 ]]; then _ok "D0: bad arg exits 2"; else _bad "D0: bad arg exits 2" "rc=$RC"; fi

echo "=== Test E: Linux substrate — /proc/meminfo yields a real RAM number ==="
if [[ -r /proc/meminfo ]]; then
    v="$(_field "$OUT" ram_available_mb)"
    if [[ "$v" =~ ^[0-9]+$ ]]; then
        _ok "E1: ram_available_mb is numeric on Linux (${v} MB)"
        if [[ "$v" -gt 0 ]]; then _ok "E2: ram_available_mb > 0"; else _bad "E2: RAM > 0" "got='${v}'"; fi
    else
        _bad "E1: numeric RAM on Linux" "got='${v}'"
        _bad "E2: RAM > 0" "got='${v}' (non-numeric)"
    fi
else
    _ok "E: skipped (no /proc/meminfo — not a Linux substrate)"
fi

echo ""
echo "========================================"
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "========================================"
if [[ "$FAIL" -gt 0 ]]; then exit 1; fi
exit 0
