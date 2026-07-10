#!/usr/bin/env bash
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
#   (5) hooks.json commands:   ARCHITECTURALLY EXEMPT (2026-06-14) — Claude Code is the CreateProcess parent; see rationale block in section (5) body below.
#   (6) powershell/pwsh:       missing -WindowStyle Hidden  (legacy check, preserved)
#
# A spawn is EXEMPT (not flagged) if any of the following are true:
#   a) The line routes through lib/spawn-hidden.sh
#   b) The line carries CREATE_NO_WINDOW, windowsHide, or -WindowStyle Hidden
#   c) The line has a trailing allowlist comment:
#        # verify-no-console-flash: allow
#      (use for: the launcher itself, this guard script, test fixtures,
#       or any spawn that is verifiably not on the Windows hot-path)
#   d) The FILE carries a header allow marker within its first 10 lines:
#        # verify-no-console-flash: file-allow — <rationale>
#      (use for: physically-Linux-only scripts — RunPod / training pipelines —
#       where no Windows conhost can be allocated regardless of spawn shape, so
#       per-line allow on 20+ interpreter calls is just noise)
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

set -euo pipefail

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
    # File-level allow: a `verify-no-console-flash: file-allow` marker in the file's
    # first 10 lines suppresses the whole file (physically-Linux-only scripts). Extract
    # the path from the `path:lineno:content` grep line drive-letter-safely — strip the
    # `:lineno:content` suffix, NOT split on the first ':' (which eats a Windows `C:`).
    local _faline_path; _faline_path="$(printf '%s' "$line" | sed -E 's/:[0-9]+:.*$//')"
    if [[ -f "$_faline_path" ]] && head -10 "$_faline_path" 2>/dev/null \
        | grep -q 'verify-no-console-flash:[[:space:]]*file-allow'; then
        return 0
    fi
    # Routes through spawn-hidden.sh (path form) or via the $_spawn_hidden variable
    # (underscore form used in session-init.sh: bash "$_spawn_hidden" --stdin-mode=safe ...).
    grep -qE 'spawn[-_]hidden' <<<"$line" && return 0
    # Explicit suppression flags
    grep -qE 'CREATE_NO_WINDOW|windowsHide|WindowStyle[[:space:]]+Hidden' <<<"$line" && return 0
    return 1
}

# ---------------------------------------------------------------------------
# Inline-comment context: drop hits where the matched interpreter token only
# appears after a `#` on the same line (it's prose, not a spawn).
# Review: code-reviewer (F4) — moved before ps_hits loop so it can be called there too.
# ---------------------------------------------------------------------------
_in_inline_comment() {
    local line="$1"
    # Strip the file:lineno: prefix so we look at source content only.
    # Review: code-reviewer (F3) — regex-anchored strip on file:lineno: shape; the
    #   simple ${line#*:*:} form was non-portable on Windows paths (drive-letter colon
    #   consumed the first '*:' segment, leaving 'lineno:content' instead of 'content').
    local content; content="$(printf '%s' "$line" | sed 's/^[^:]*:[0-9][0-9]*://')"
    # Take everything up to the first `#` (code part).
    local code_part="${content%%#*}"
    # If the code part still contains a spawn shape, NOT in comment.
    # Review: code-reviewer (F4) — extended to also recognise powershell.exe/pwsh tokens
    #   so the helper covers the ps_hits loop as well as the py_node_hits loop.
    if echo "$code_part" | grep -qE \
        -e '\$\{(PYTHON|NODE)[^}]*\}' \
        -e '\$(PYTHON|NODE)[A-Z_0-9]*' \
        -e '(^|[[:space:]])python3?[[:space:]]' \
        -e '(^|[[:space:]])node[[:space:]]' \
        -e 'python3?[[:space:]]+-[ce][[:space:]]' \
        -e 'node[[:space:]]+-e[[:space:]]' \
        -e 'powershell\.exe[[:space:]]' \
        -e '(^|[[:space:]/])pwsh[[:space:]]'; then
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# (6) powershell / pwsh without -WindowStyle Hidden  (legacy shape)
# ---------------------------------------------------------------------------
ps_hits=()
while IFS= read -r line; do ps_hits+=("$line"); done < <(
    grep -rEn --include='*.sh' --include='*.json' --include='coordinator-auto-push' \
        -e 'powershell\.exe[[:space:]]' -e '(^|[[:space:]/])pwsh[[:space:]]' \
        "$COORD_ROOT" 2>/dev/null \
    | grep -v 'verify-no-console-flash\|verify-no-powershell-flash' \
    | grep -vE ':[[:space:]]*[0-9]+:[[:space:]]*#' \
    | grep -vE 'command[[:space:]]+-v[[:space:]]+(pwsh|powershell\.exe|powershell)\b' \
    | grep -vE '(^|[[:space:];|&(])echo[[:space:]]+"[^"]*powershell\.exe[^"]*"' \
    || true
    # F5 (2026-06-15, plan closure pass) — ps_hits previously had no FP prefilter
    #   beyond _in_inline_comment. Three classes were leaking through:
    #     (a) capability detection `command -v powershell.exe`
    #     (b) full-line `# comment` lines whose post-strip content has `powershell.exe`
    #         token (covered by _in_inline_comment but the leading-`#` line shape
    #         is cheaper to drop here)
    #     (c) echo-message strings containing powershell.exe inside double quotes
    #   These mirror the py_node_hits filter set so the two sections stay symmetric.
)

for line in "${ps_hits[@]}"; do
    # Review: code-reviewer (F4) — skip lines where the powershell/pwsh token only
    #   appears inside an inline comment (prose, not a real spawn call).
    if _in_inline_comment "$line"; then
        continue
    fi
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
py_node_hits=()
while IFS= read -r line; do py_node_hits+=("$line"); done < <(
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
    | grep -vE 'verify-no-console-flash|verify-no-powershell-flash' \
    | grep -vE 'command[[:space:]]+-v[[:space:]]+(python|node)' \
    | grep -vE 'command[[:space:]]+-v[[:space:]]+"?\$\{?(PYTHON|NODE)' \
    | grep -vE ':[[:space:]]*[0-9]+:[[:space:]]*#' \
    | grep -vE '\[\[[[:space:]]+-[zn][[:space:]]+"?\$\{?(PYTHON|NODE)' \
    | grep -vE '(^|[[:space:];|&(])\[[[:space:]]+-[zn][[:space:]]+"?\$\{?(PYTHON|NODE)' \
    | grep -vE '\bfor[[:space:]]+[A-Za-z_][A-Za-z_0-9]*[[:space:]]+in[[:space:]]+[^|;&]*\b(python3?|node)\b' \
    | grep -vE 'Get-Command[[:space:]]+(python3?|node|py)\b' \
    | grep -vE '(^|[[:space:];|&(])echo[[:space:]]+"[^"]*\b(python3?|node)\b[^"]*"' \
    | grep -vE '(^|[[:space:];|&(])echo[[:space:]]+"[^"]*(Python|Node\.js|Nodejs)\b[^"]*"' \
    | grep -vE '\$\{?(NODE|PYTHON)_(VERSION|MIN_VERSION|MAJOR|MINOR|HOME|MODULES|JS|EXEC|TAG|REQUIREMENT|TARGET|MIN|SHIM|SHIM_WIN|CMD|REL|DIR|TYPE)\b' \
    | grep -vE '\[\[?[[:space:]]+"?\$\{?[a-zA-Z_][a-zA-Z_0-9]*\}?"?[[:space:]]+-(lt|gt|le|ge|eq|ne)\b' \
    | grep -vE '\$\{PYTHON_ARGS\[' \
    | grep -vE '\$\{NODE_ARGS\[' \
    | grep -vE '^[^:]*:[0-9]+:[[:space:]]*(local[[:space:]]+|export[[:space:]]+)?(NODE|PYTHON)[A-Z_0-9]*=' \
    | grep -vE '^[^:]*:[0-9]+:[[:space:]]*(local[[:space:]]+|export[[:space:]]+)?[a-z][a-zA-Z_0-9]*="\$\(' \
    | grep -vE '(^|[[:space:];|&(])(fail|warn|info|die|log|error|print|printf)[[:space:]]+"[^"]*\b(python3?|node|Python|Node)\b' \
    | grep -vE '^[^:]*:[0-9]+:[[:space:]]*[A-Z_][A-Z_0-9]*="[^"]*\b(python3?|node|Python|Node)\b' \
    | grep -vE '^[^:]*:[0-9]+:[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*"' \
    | grep -vE '\bread[[:space:]]+-ra?[[:space:]]' \
    || true
    # F6 (2026-06-27) — two additional false-positive classes:
    #   (g) config/TOML key-value assignments inside heredocs: `python = "/path/..."` is a
    #       string value, not a spawn head. Pattern: `identifier = "..."` shape where the
    #       content after file:lineno: is a bare key = "value" assignment.
    #       Catches test fixture TOML at test-check-install-singularity.sh:142.
    #   (h) IFS-prefixed `read -ra VAR <<< "$PYTHON"` array-split idiom — the $PYTHON token
    #       is the source value being split into an array, not an interpreter being spawned.
    #       Catches generate-repomap.sh:70 `IFS=' ' read -ra PYTHON_CMD <<< "$PYTHON"`.
    # F1 — pre-filter `command -v python|node` availability-check idioms.
    # F2 — pre-filter pure-comment lines (file:lineno: followed by whitespace+#).
    # F3 (2026-06-14) — use grep -vE so [[:space:]]+ behaves as ERE quantifier; prior
    #   BRE form treated `+` as literal, silently no-op'ing both filters.
    # F4 (2026-06-14, memo console-flash-guard-coord-tree-unsuppressed) — drop
    #   four non-spawn shapes that surfaced as false-positives on a wider scan:
    #     (a) emptiness tests `[[ -z "$PYTHON_BIN" ]]` / `[[ -n "${NODE:-}" ]]`
    #     (b) for-loops over interpreter literals `for c in python3 python py`
    #     (c) powershell `Get-Command python` probes — literal interpreter token
    #         only (python3?/node/py). Variable-form `Get-Command $PYTHON_BIN`
    #         is intentionally NOT suppressed: variable-form probes are absent
    #         from the current tree and a future variable-form *spawn* must
    #         continue to flag.
    #     (d) echo-message strings carrying the interpreter token inside double quotes
    #         (e.g. `echo "no python interpreter ..."`, `echo "SKIP python3 ..."`).
    #   Filters (b) and (d) are deliberately NOT end-of-line-anchored — real
    #   tree shapes have legitimate trailing content (`for c in python3 python py; do`
    #   ends with `; do`; `echo "..." >&2` ends with a redirect). An anchor that
    #   caught a contrived `echo "msg" ; python script.py` compound line would
    #   regress both. The compound-spawn-after-quote shape is a theoretical risk
    #   not observed in the tree; the spawn after `; do` in a for-body is a
    #   SEPARATE line and processed independently by the per-line grep.
    #   These are pattern-level false-positives, not source-code defects — tightening
    #   here keeps the named sites clean rather than annotating each with `# allow`.
    # F5 (2026-06-15, plan closure pass) — six new FP filter classes surfaced when
    #   driving the guard to a clean baseline across the full coordinator tree:
    #     (a) variable-form `command -v "$PYTHON_BIN"` (literal-form filter existed)
    #     (b) single-bracket POSIX emptiness test `[ -z "$PYTHON" ]` ([[ form existed)
    #     (c) capitalised / Node.js echo-message strings (lowercase form existed)
    #     (d) value-shaped variable names: $NODE_VERSION, $PYTHON_MAJOR, $NODE_MIN — these
    #         are values being read, not interpreters being spawned. The regex enumerates
    #         the suffixes we actually see in the tree; unfamiliar value-shaped suffixes
    #         must extend this list, not weaken the matcher.
    #     (e) numeric comparisons `[[ "$node_major" -lt N ]]` — the matched interpreter
    #         token only appears in a comparison operand, never as a command head.
    #     (f) resolve-python.sh callers: `"$PYTHON_BIN" "${PYTHON_ARGS[@]}"` is the
    #         documented idiom for the resolver, which returns pythonw*.exe on Windows
    #         → already windowless. The presence of "${PYTHON_ARGS[..." on the line is
    #         a load-bearing signal the caller is using the resolver. NOTE this is
    #         safe ONLY because resolve-python.sh's own stdin-safety caveat (line 35)
    #         keeps harness-piped-stdin children OUT of the resolver — those must use
    #         lib/spawn-hidden.sh and won't carry the PYTHON_ARGS marker.
    #
    #         INVARIANT (code-reviewer F3, 2026-06-15): Any caller declaring a
    #         `PYTHON_ARGS` or `NODE_ARGS` array MUST source it from `resolve-python.sh`
    #         (or a future analogous resolver lib). A future declaration of these
    #         identifiers for any OTHER purpose MUST rename the variable — otherwise
    #         the new caller is silently exempted by this filter without any actual
    #         suppression. This is a naming-convention invariant, not a structural
    #         check; the filter trusts the name. If a peer-repo lifts this guard
    #         without `resolve-python.sh`, drop the (f) filter or replace it with a
    #         structural check (e.g. require the calling script to source the lib).
    #
    #         Conversely: `$PYTHON_BIN` / `$NODE_BIN` used as a SPAWN HEAD without
    #         the `${PYTHON_ARGS[@]}` splat is intentionally NOT suppressed by this
    #         pass (code-reviewer F5). That spawn shape bypasses the resolver idiom
    #         and SHOULD be flagged — annotate explicitly (`# verify-no-console-flash:
    #         allow <reason>`) if the script is verifiably not on the Windows hot-path.
)

for line in "${py_node_hits[@]}"; do
    if _in_inline_comment "$line"; then
        continue
    fi
    if ! _is_suppressed "$line"; then
        echo "UNSUPPRESSED python/node spawn: $line"
        fail=1
    fi
done

# ---------------------------------------------------------------------------
# (5) hooks.json command strings — ARCHITECTURALLY EXEMPT (2026-06-14)
# ---------------------------------------------------------------------------
# Claude Code itself is the CreateProcess parent for hook command spawns. The
# shell-level launcher (lib/spawn-hidden.sh) cannot influence the parent's
# CreateProcess flags. Per spawn-hidden.sh § MECHANISM LIMITS, harness-piped-
# stdin children are unsuppressible from shell — true suppression requires
# Claude Code to pass windowsHide:true / CREATE_NO_WINDOW at its own spawn site
# (upstream fix), the machine-belt ConPTY delegation (Chunk 5), or a compiled
# shim (plan Addendum).
#
# Flagging hooks.json command lines here produces noise without an actionable
# shell-level fix. The check is removed; the doctrinal answer is logged in the
# improvement queue for the upstream/machine-belt resolution path.
#
# History: removed after example-game-repo-em fyi memo 2026-06-14 surfaced 3 hooks.json
# hits in our tree. Cross-tree pattern confirmed: shell-channel suppression
# is structurally bounded; harness-owned spawns are out of scope for this guard.

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
if [[ "$fail" -eq 0 ]]; then
    echo "OK: all console-spawning invocations are suppressed or explicitly allowlisted"
fi

exit "$fail"
