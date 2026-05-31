#!/bin/bash
# verify-no-console-flash.sh — guard against console-window flashes on Windows.
#
# On Windows (git-bash/mintty), spawning any native console-subsystem .exe
# (python.exe, node.exe, powershell.exe) allocates a fresh conhost.exe window
# that briefly flashes. The only reliable suppression is CREATE_NO_WINDOW /
# windowsHide:true at the CreateProcess call — not -WindowStyle Hidden, which
# is create-then-hide. See: docs/wiki/claude-code-platform-gotchas.md
# § Windows console window flash.
#
# Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 3
#
# This guard flags any of the following spawn shapes when they lack an explicit
# suppression flag or routing through lib/spawn-hidden.sh:
#   (1) variable-interpreter:  "${PYTHON:-python3}", "$PYTHON", $PYTHON_BIN, "${NODE...}"
#   (2) heredoc spawn:         interpreter token followed by ' - ' and/or '<<'
#                              e.g. "${PYTHON:-python3}" - "$pname" "$reg_file" <<'PYEOF'
#   (3) bare literals:         python , python3 , node  (with trailing space)
#   (4) array-form / flags:    python -c / node -e / python3 -c
#   (5) hooks.json commands:   "command": "python ..." / "node ..."
#   (6) powershell/pwsh:       missing -WindowStyle Hidden  (legacy check, preserved)
#
# A spawn is EXEMPT (not flagged) if any of the following are true:
#   a) The line routes through lib/spawn-hidden.sh
#   b) The line carries CREATE_NO_WINDOW, windowsHide, or -WindowStyle Hidden
#   c) The line has a trailing allowlist comment:
#        # verify-no-console-flash: allow
#      (use for: the launcher itself, this guard script, test fixtures,
#       or any spawn that is verifiably not on the Windows hot-path)
#
# IMPORTANT — live-tree state:
#   As of Wave 2 execution, the live tree still contains unsuppressed spawns in
#   the 4 venv-check heredocs at check-plugin-drift.sh ~286/343/373/426 (which
#   use bare $PYTHON for stdin=safe heredoc spawns) AND $PYTHON_BIN spawns in
#   lib/coordinator-session.sh (~100/271/601). Running this guard against the
#   live tree WILL report those violations until Wave 2.5 lands.
#   That is correct behaviour — the guard is working.
# Review: code-reviewer (F4-comment) — corrected from stale line-513 reference;
#   513 was already collapsed+routed in Wave 2. Actual remaining targets named above.
#
# Usage:
#   bin/verify-no-console-flash.sh [ROOT]
#   ROOT defaults to $HOME/.claude/plugins
#
# Exits 0 if all sites are clean, 1 with a report otherwise.
# Scans *.sh, *.json, and coordinator-auto-push under coordinator-claude tree.

set -uo pipefail

ROOT="${1:-$HOME/.claude/plugins}"
COORD_ROOT="$ROOT/coordinator-claude"
fail=0

# ---------------------------------------------------------------------------
# Helper: check if a matched line carries an explicit suppression or allowlist
# ---------------------------------------------------------------------------
_is_suppressed() {
    local line="$1"
    # Allowlist marker (trailing comment)
    grep -q 'verify-no-console-flash:[[:space:]]*allow' <<<"$line" && return 0
    # Routes through spawn-hidden.sh
    grep -q 'spawn-hidden' <<<"$line" && return 0
    # Explicit suppression flags
    grep -qE 'CREATE_NO_WINDOW|windowsHide|WindowStyle[[:space:]]+Hidden' <<<"$line" && return 0
    return 1
}

# ---------------------------------------------------------------------------
# (6) powershell / pwsh without -WindowStyle Hidden  (legacy shape)
# ---------------------------------------------------------------------------
mapfile -t ps_hits < <(
    grep -rEn --include='*.sh' --include='*.json' --include='coordinator-auto-push' \
        -e 'powershell\.exe[[:space:]]' -e '(^|[[:space:]/])pwsh[[:space:]]' \
        "$COORD_ROOT" 2>/dev/null \
    | grep -v 'verify-no-console-flash\|verify-no-powershell-flash' \
    || true
)

for line in "${ps_hits[@]}"; do
    if ! _is_suppressed "$line"; then
        echo "MISSING -WindowStyle Hidden (powershell/pwsh): $line"
        fail=1
    fi
done

# ---------------------------------------------------------------------------
# (1–4) python / node spawn shapes in shell scripts and helper bins
#
# Patterns caught:
#   \$\{PYTHON[^}]*\}   — "${PYTHON:-python3}", "${PYTHON_BIN:-...}", etc.
#   \$PYTHON[A-Z_]*     — $PYTHON, $PYTHON_BIN, $PYTHON3
#   \$\{NODE[^}]*\}     — "${NODE:-node}", etc.
#   \$NODE[A-Z_]*       — $NODE_BIN
#   (^|[[:space:]])python3?[[:space:]]   — bare "python " / "python3 "
#   (^|[[:space:]])node[[:space:]]       — bare "node "
#   python3?[[:space:]]-[ce][[:space:]]  — python -c / python3 -c / python -e
#   node[[:space:]]-e[[:space:]]         — node -e
#
# The heredoc shape "${PYTHON:-python3}" - "$x" <<'...' is matched by the
# variable-interpreter pattern above — the ' - ' suffix is part of the line.
# ---------------------------------------------------------------------------
mapfile -t py_node_hits < <(
    grep -rEn --include='*.sh' --include='coordinator-auto-push' \
        -e '\$\{PYTHON[^}]*\}' \
        -e '\$PYTHON[A-Z_0-9]*' \
        -e '\$\{NODE[^}]*\}' \
        -e '\$NODE[A-Z_0-9]*' \
        -e '(^|[[:space:]])python3?[[:space:]]' \
        -e '(^|[[:space:]])node[[:space:]]' \
        -e 'python3?[[:space:]]+-[ce][[:space:]]' \
        -e 'node[[:space:]]+-e[[:space:]]' \
        "$COORD_ROOT" 2>/dev/null \
    | grep -v 'verify-no-console-flash\|verify-no-powershell-flash' \
    | grep -v 'command[[:space:]]+-v[[:space:]]+python' \
    | grep -v ':[[:space:]]*#' \
    || true
    # Review: code-reviewer (F1) — pre-filter `command -v python3?` detection idioms to
    #   avoid false positives on availability-check lines (e.g. check-plugin-drift.sh:52-54,
    #   resolve-python.sh, test-spawn-hidden.sh, coordinator-doctor-sentinel.sh).
    # Review: code-reviewer (F2) — filter pure comment lines (content after file:lineno:
    #   prefix starts with #) to avoid flagging commented-out code.
)

for line in "${py_node_hits[@]}"; do
    if ! _is_suppressed "$line"; then
        echo "UNSUPPRESSED python/node spawn: $line"
        fail=1
    fi
done

# ---------------------------------------------------------------------------
# (5) hooks.json command strings containing python or node invocations
# ---------------------------------------------------------------------------
mapfile -t json_hits < <(
    grep -rEn --include='*.json' \
        -e '"command"[[:space:]]*:[[:space:]]*"(python|python3|node)[[:space:]]' \
        "$COORD_ROOT" 2>/dev/null \
    | grep -v 'verify-no-console-flash\|verify-no-powershell-flash' \
    || true
)

for line in "${json_hits[@]}"; do
    if ! _is_suppressed "$line"; then
        echo "UNSUPPRESSED hooks.json command (python/node): $line"
        fail=1
    fi
done

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
if [[ "$fail" -eq 0 ]]; then
    echo "OK: all console-spawning invocations are suppressed or explicitly allowlisted"
fi

exit "$fail"
