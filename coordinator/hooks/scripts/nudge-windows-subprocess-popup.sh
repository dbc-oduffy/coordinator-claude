#!/usr/bin/env bash
# verify-no-console-flash: file-allow — this IS the C2 authoring-deny hook; interpreter
# tokens in REASON/detection strings below are advisory text and patterns, not spawns.
# PreToolUse(Write|Edit|MultiEdit) hook: denies authoring of bare console-subprocess
# calls in .sh/.py/.ps1/.psm1 files and offers the popup-safe alternative.
#
# Motivation: Windows console-subsystem children (python.exe, powershell.exe) spawned
# from the headless Claude Code Bash-tool parent call AllocConsole() and steal focus.
# At AUTHORING time the PORTABLE suppression form — creationflags=getattr(subprocess,
# "CREATE_NO_WINDOW", 0) — is a stdlib one-liner available everywhere, prompt-free, no
# project dependency. CAUTION: a bare creationflags=0x08000000 (or an unguarded
# subprocess.CREATE_NO_WINDOW) is NOT portable — it raises ValueError off-Windows and the
# attribute is absent there, so the offer MUST show the getattr form. The portable form is
# what satisfies the "universal prompt-free equivalent safe to force" condition that
# justifies deny-with-offer per eager-agent-calibration.md § Offer-Shape vs Friction-as-Warning.
#
# C1-allow vs C2-deny rationale: C1 (Bash execution hook) allows + advises because the
# popup-safe runtime alternative (python-quiet.sh) is project-specific and may not exist.
# C2 (this hook) DENIES because the portable suppression one-liner (the getattr form above)
# IS universally available at authoring time. The asymmetry is intentional and must not be
# conflated. Deny-with-offer is legitimate ONLY because the offer is verified-portable on the
# host that receives the deny — see docs/wiki/cross-platform-shell-portability.md
# § Platform-conditional guard taxonomy.
#
# Does NOT Windows-gate: a script authored on macOS runs on Windows. Authoring-time risk
# is unconditional — the code goes to disk regardless of current platform.
#
# Allowlist escape: TWO canonical, env-agnostic suppression markers are honored identically:
#   `# popup-intentional-last-resort`  — the console popup occurs and is accepted (pythonw
#                                         fallback / genuine console need).
#   `# popup-safe-env-suppressed`      — the popup is suppressed at this site by env-var
#                                         means (safe; env isolation guarantees no popup).
# The retired `# noqa: bare-subprocess-windows` form stays retired.
# Matches project-rag's enforced C5 tripwire vocabulary.
#
# Spec backlink: docs/plans/2026-06-19-windows-console-popup-coordinator-doctrine.md § C2
# Tripwire entry: docs/wiki/coordinator-tripwires.md § NUDGE-WINDOWS-SUBPROCESS-POPUP
# DR-148: must run on bash 3.2 + BSD coreutils (no grep -P, no sed -i, no date -d,
#         no GNU-only builtins)
#
# Decision mechanism (Form A): emit permissionDecision:"deny" to STDOUT, exit 0.
# Allow: exit 0, no stdout.

set -uo pipefail
# -e deliberately omitted — offer hooks must fail-open on unexpected error.

# Review: code-reviewer (F6) — sys.executable is listed as a detection target in the
# comment above the detection block, but it is detected by the grep pattern on line ~161.
# Note: sys.executable resolves to the python interpreter path (often python.exe on Windows),
# so the pattern "sys\.executable" in the detection grep covers it. No code change needed.
#
# Review: code-reviewer (F3) — git.exe is intentionally excluded: git always spawns
# with DETACHED_PROCESS semantics on Windows and does not call AllocConsole() in the
# relevant context. Adding git.exe to detection would cause false positives on common
# subprocess.run(["git.exe", ...]) patterns that are inherently safe.
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

# --- Safe stdin read (timeout guard prevents hang on Windows/Git Bash) ---
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat || true)
fi

# --- Parse tool_name (jq -> python -> sed cascade) ---
if command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
elif [[ -n "$PY" ]]; then
  TOOL_NAME=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
else
  # Review: code-reviewer (F4) — sed|head pipeline lacks || true under set -uo pipefail;
  # a non-zero exit kills the hook (fails closed). Append || true to match fail-open contract.
  TOOL_NAME=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 || true)
fi

# Only act on file-mutation tools.
case "$TOOL_NAME" in
  Write|Edit|MultiEdit) : ;;
  *) exit 0 ;;
esac

# --- Parse file_path (jq -> python -> sed cascade) ---
if command -v jq >/dev/null 2>&1; then
  FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
elif [[ -n "$PY" ]]; then
  FILE_PATH=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("file_path","")))' 2>/dev/null || true)
else
  # Review: code-reviewer (F4) — same fail-open fix; sed|head needs || true.
  FILE_PATH=$(printf '%s' "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1 || true)
fi

[[ -z "$FILE_PATH" ]] && exit 0

# Normalize backslashes (Windows path support).
FILE_PATH="${FILE_PATH//\\//}"

# --- Extension gate: only .sh / .py / .ps1 / .psm1 ---
case "$FILE_PATH" in
  *.sh|*.py|*.ps1|*.psm1) : ;;
  *) exit 0 ;;
esac

# --- Throwaway-path exemption (Option A, 2026-06-20 — see § Platform-conditional guard
#     taxonomy). The authoring-time deny exists because authored code SHIPS to Windows.
#     Session-scratch under tasks/ and state/scratch/ is throwaway flight-recorder / driver
#     code that runs only on the author's own machine and is never shipped to a Windows
#     operator — so the authoring rationale does not apply, and denying it is pure friction
#     (the dominant false-positive: a sys.executable re-invoke harness in a tasks/ driver,
#     per the 2026-06-20 project-rag-ue-addon memo). Runtime execution on a Windows author's
#     OWN box is still covered by the C1 Bash-execution hook. Production paths keep the deny.
case "$FILE_PATH" in
  */tasks/*|*/state/scratch/*) exit 0 ;;
esac

# --- Extract content to scan (tool-type-specific) ---
# Write: tool_input.content
# Edit: tool_input.new_string
# MultiEdit: concatenate all edits[].new_string values
CONTENT=""

case "$TOOL_NAME" in

  Write)
    if command -v jq >/dev/null 2>&1; then
      CONTENT=$(printf '%s' "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null || true)
    elif [[ -n "$PY" ]]; then
      CONTENT=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("content","")))' 2>/dev/null || true)
    else
      # no-parser fallback: scan raw JSON body.
      CONTENT=$(printf '%s' "$INPUT")
    fi
    ;;

  Edit)
    if command -v jq >/dev/null 2>&1; then
      CONTENT=$(printf '%s' "$INPUT" | jq -r '.tool_input.new_string // empty' 2>/dev/null || true)
    elif [[ -n "$PY" ]]; then
      CONTENT=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_input",{}).get("new_string","")))' 2>/dev/null || true)
    else
      CONTENT=$(printf '%s' "$INPUT")
    fi
    ;;

  MultiEdit)
    if command -v jq >/dev/null 2>&1; then
      CONTENT=$(printf '%s' "$INPUT" | jq -r '[.tool_input.edits[]?.new_string // ""] | join("\n")' 2>/dev/null || true)
    elif [[ -n "$PY" ]]; then
      CONTENT=$(printf '%s' "$INPUT" | "$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
edits=d.get("tool_input",{}).get("edits",[])
sys.stdout.write("\n".join(str(e.get("new_string","")) for e in edits))' 2>/dev/null || true)
    else
      CONTENT=$(printf '%s' "$INPUT")
    fi
    ;;

esac

[[ -z "$CONTENT" ]] && exit 0

# --- Allowlist escape (canonical cross-layer markers) ---
case "$CONTENT" in
  *'# popup-intentional-last-resort'*|*'# popup-safe-env-suppressed'*) exit 0 ;;
esac

# --- Detection: file-type-specific patterns ---
# Returns 1 (match) or 0 (no match) via SHOULD_DENY flag.
SHOULD_DENY=0

case "$FILE_PATH" in

  *.sh|*.py)
    # Python subprocess.run / Popen / os.system with console-subsystem child lacking suppression.
    # Check: call to subprocess.run( / subprocess.Popen( / os.system( present.
    # Check: references a console-subsystem exe (powershell.exe / netstat.exe / python.exe /
    #        cmd.exe / sys.executable).
    # Allow-guard: creationflags= / CREATE_NO_WINDOW / no_console_creationflags() present
    #              in the content — suppression already provided.
    #
    # Shell-file check: bare `python -c` / `python3 -c` / `powershell.exe` tokens.
    # BSD-portable grep: use grep -E (not -P); no lookaheads.

    # Check for Python subprocess calls with console children.
    if printf '%s' "$CONTENT" | grep -qE 'subprocess\.(run|Popen)\(|os\.system\('; then
      if printf '%s' "$CONTENT" | grep -qE '"(powershell\.exe|netstat\.exe|python\.exe|cmd\.exe)"|sys\.executable'; then
        # Check if suppression is already present.
        if ! printf '%s' "$CONTENT" | grep -qE 'creationflags=|CREATE_NO_WINDOW|no_console_creationflags\(\)'; then
          SHOULD_DENY=1
        fi
      fi
    fi

    # Shell-file bare python / powershell invocations (applies to .sh and .py).
    if [[ "$SHOULD_DENY" -eq 0 ]]; then
      if printf '%s' "$CONTENT" | grep -qE '(^|[[:space:];&|`])(python3?(\.exe)?[[:space:]]+(-c|-m)|powershell\.exe)'; then
        # Allow if suppression marker or safe variant is already present.
        # Python suppressors: creationflags / CREATE_NO_WINDOW / wrapper / pythonw.
        # PowerShell suppressor: `-WindowStyle Hidden` — the canonical fix this
        # hook's own offer text recommends, already honored by the *.ps1 branch
        # below and by bin/verify-no-console-flash.sh (its Test 5). Omitting it
        # here denied legitimately-suppressed powershell.exe calls authored in
        # .sh files (e.g. install-substrate.sh Windows PATH integration).
        if ! printf '%s' "$CONTENT" | grep -qiE 'creationflags=|CREATE_NO_WINDOW|no_console_creationflags\(\)|python-quiet\.sh|pythonw|-WindowStyle[[:space:]]+Hidden'; then
          SHOULD_DENY=1
        fi
      fi
    fi
    ;;

  *.ps1|*.psm1)
    # PowerShell bare-call patterns lacking suppression.
    # Bare: `& python`, `python.exe -c`, `Invoke-Expression "python ..."`,
    #       bare `powershell.exe`/`pwsh` without `-WindowStyle Hidden`.

    if printf '%s' "$CONTENT" | grep -qiE '&[[:space:]]+python(\.exe)?|python\.exe[[:space:]]+-c|Invoke-Expression[[:space:]]+"python|Invoke-Expression[[:space:]]+'\''python'; then
      SHOULD_DENY=1
    fi

    if [[ "$SHOULD_DENY" -eq 0 ]]; then
      if printf '%s' "$CONTENT" | grep -qiE '(^|[[:space:]])(powershell\.exe|pwsh)([[:space:]]|$)'; then
        if ! printf '%s' "$CONTENT" | grep -qiE '\-WindowStyle[[:space:]]+Hidden'; then
          SHOULD_DENY=1
        fi
      fi
    fi
    ;;

esac

[[ "$SHOULD_DENY" -eq 0 ]] && exit 0

# --- Deny function (Form A) ---
deny() {
  local reason="$1"
  if command -v jq >/dev/null 2>&1; then
    jq -nc --arg r "$reason" \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [[ -n "$PY" ]]; then
    local rj
    rj=$(printf '%s' "$reason" | "$PY" -c 'import json,sys;sys.stdout.write(json.dumps(sys.stdin.read()))' 2>/dev/null) \
      || rj="\"$(printf '%s' "$reason" | tr '\n' ' ' | sed 's/\\/\\\\/g; s/"/\\"/g')\""
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":%s}}\n' "$rj"
  else
    local esc
    esc="${reason//\\/\\\\}"; esc="${esc//\"/\\\"}"; esc="${esc//$'\n'/\\n}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$esc"
  fi
  exit 0
}

# Review: code-reviewer (F5) — no-parser fallback in deny() applies one-pass escape
# (sed s/\\/\\\\/g; s/"/\\"/g). Pre-escaped \" in REASON were double-escaped to \\"
# in that path. Fix: author REASON without \" — use literal " chars so the single
# escape pass produces correct JSON in all three paths (jq / python / no-parser).
REASON='OFFER: Add CREATE_NO_WINDOW to suppress the Windows console popup.

The file being written contains a bare console-subprocess call (subprocess.run/Popen/os.system with powershell.exe/python.exe/cmd.exe, or bare powershell.exe/& python in PowerShell) that will call AllocConsole() and steal focus when run under the headless Claude Code Bash-tool parent on Windows.

RECOMMENDED FIX (Python) -- use the PORTABLE form (safe on Windows AND macOS/Linux):
  import subprocess
  subprocess.run(["powershell.exe", ...],
                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

  Do NOT write a bare creationflags=0x08000000 / subprocess.CREATE_NO_WINDOW -- that
  raises ValueError on macOS/Linux (the attribute is Windows-only). The getattr form
  resolves to CREATE_NO_WINDOW on Windows and 0 (no-op) on every other platform.

  Or if the project provides no_console_creationflags():
  subprocess.run(["powershell.exe", ...], **no_console_creationflags())

RECOMMENDED FIX (PowerShell):
  powershell.exe -WindowStyle Hidden -Command ...
  pwsh -WindowStyle Hidden -Command ...

WHY: creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) is a stdlib one-liner
that is safe on every OS -- no project dependency required. (The bare 0x08000000 /
subprocess.CREATE_NO_WINDOW form is NOT safe: it raises ValueError off-Windows.) The
portable form is the zero-dependency safe alternative that justifies authoring-time denial.

Spec backlink: docs/plans/2026-06-19-windows-console-popup-coordinator-doctrine.md § C2
             ; docs/plans/2026-06-22-popup-suppression-marker-two-vocabulary-reconcile.md § The decision this plan implements

ALLOWLIST ESCAPE: Add one of the two canonical suppression markers on the relevant line:
  subprocess.run(["powershell.exe", ...])  # popup-intentional-last-resort
    Use this when the popup occurs and is genuinely accepted (pythonw fallback, console need).
  subprocess.run(["powershell.exe", ...])  # popup-safe-env-suppressed
    Use this when the popup is suppressed at this site by env-var means (safe).'

deny "$REASON"
