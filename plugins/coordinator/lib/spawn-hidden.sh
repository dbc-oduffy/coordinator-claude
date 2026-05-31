#!/bin/bash
# spawn-hidden.sh — Windows-console-window-suppressing launcher for coordinator scripts.
#
# Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 1
#
# PURPOSE
# -------
# On Windows, spawning a native console-subsystem .exe (python.exe, node.exe,
# powershell.exe) from mintty / Git Bash causes Windows to allocate a fresh
# conhost.exe console window for the child, producing a visible flash.
#
# This launcher attempts to suppress that flash using the best mechanism
# available FROM A SHELL CONTEXT.  The caller declares, via --stdin-mode,
# whether the child will read a live OS-level stdin pipe from an external
# harness (e.g. a Claude Code PreToolUse hook reading tool-call JSON) or
# whether stdin is caller-controlled (heredoc, /dev/null, args-only).
#
# MECHANISM LIMITS — READ THIS BEFORE WIRING NEW CALL SITES
# -----------------------------------------------------------
# A pure bash launcher CANNOT set the Win32 CREATE_NO_WINDOW
# (dwCreationFlags=0x08000000) bit.  That bit can only be set at the
# CreateProcess() call made by the *spawning parent*.  Here is what each
# path actually does:
#
#   --stdin-mode=safe   (caller controls stdin — heredoc / /dev/null / args)
#     On Windows: resolve to pythonw.exe / pyw.exe (SUBSYSTEM:WINDOWS binary).
#     That binary is byte-for-byte identical to python.exe but built with
#     /SUBSYSTEM:WINDOWS, so Windows does NOT allocate a console window for it.
#     THIS IS GENUINE SUPPRESSION for this class of spawn.
#     *** SAFE ONLY when the EM / script provides stdin via heredoc or redirect.
#     *** DO NOT use for children that read the harness's live pipe on stdin.
#
#   --stdin-mode=safe (node)
#     There is no "nodew.exe" equivalent.  The launcher falls through to the
#     non-suppressing path and documents the gap.  True node suppression
#     requires the SPAWNING PARENT to pass windowsHide:true to child_process
#     (only applies to spawns the Node process itself makes) or CREATE_NO_WINDOW
#     via a compiled shim (see plan Addendum).
#
#   --stdin-mode=pipe   (child reads live harness-piped stdin)
#     A bash launcher CANNOT suppress the console window for this class:
#     - pythonw.exe is UNSAFE here — SUBSYSTEM:WINDOWS binaries may receive a
#       null/invalid stdin handle from a console-less parent.  sys.stdin reads
#       raise ValueError/EOFError; the bare except in check-claude-md-size.py
#       catches and exits 0, silently disabling the gate.
#     - No other shell-level suppression flag exists.
#     HONEST RESULT: for harness-piped-stdin children, this launcher passes
#     through the invocation unchanged (inheriting stdin/stdout/stderr and
#     propagating exit code) but does NOT suppress the console flash.
#     Suppression for these sites requires the machine-belt (Chunk 5 —
#     Windows Terminal ConPTY delegation change) or a compiled C# shim
#     (plan Addendum).
#
#   Non-Windows
#     No console allocation occurs; launcher exec's directly — transparent.
#
# USAGE
# -----
#   source lib/spawn-hidden.sh    # not intended — use as a standalone launcher
#
#   lib/spawn-hidden.sh [--stdin-mode=safe|pipe] <interpreter> [args...]
#
#   --stdin-mode=safe   Child's stdin is caller-controlled (heredoc, /dev/null,
#                       args-only).  On Windows, attempt windowless binary for
#                       python; for node, no suppression available (documented).
#   --stdin-mode=pipe   Child reads a live OS-level stdin pipe from an external
#                       harness.  No console suppression attempted (would break
#                       stdin); launcher exec's transparently.
#   Default: --stdin-mode=pipe (conservative — prefer correctness over flash
#            suppression when the caller does not declare intent).
#
# EXIT CODE
# ---------
#   Propagates the child's exit code exactly.
#
# STDIN / STDOUT / STDERR
# -----------------------
#   Fully inherited from the launcher's own handles — the child gets exactly
#   what the launcher got.  No buffering, no redirection.

set -euo pipefail

STDIN_MODE="pipe"   # conservative default: never risk breaking stdin

# Parse --stdin-mode flag
while [[ $# -gt 0 ]]; do
  case "$1" in
    --stdin-mode=safe) STDIN_MODE="safe"; shift ;;
    --stdin-mode=pipe) STDIN_MODE="pipe"; shift ;;
    --stdin-mode=*)
      echo "spawn-hidden.sh: unknown --stdin-mode value: $1" >&2
      exit 1
      ;;
    --) shift; break ;;
    *) break ;;
  esac
done

if [[ $# -eq 0 ]]; then
  echo "spawn-hidden.sh: no interpreter specified" >&2
  echo "Usage: spawn-hidden.sh [--stdin-mode=safe|pipe] <interpreter> [args...]" >&2
  exit 1
fi

INTERPRETER="$1"
shift
ARGS=("$@")

# ------------------------------------------------------------------
# Platform detection
# ------------------------------------------------------------------
_on_windows() {
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*|Windows*) return 0 ;;
    *) return 1 ;;
  esac
}

# ------------------------------------------------------------------
# Resolve a windowless Python binary (SUBSYSTEM:WINDOWS variant).
# Returns the resolved binary name via stdout, or empty string if none found.
# Only safe when --stdin-mode=safe (caller controls stdin).
# ------------------------------------------------------------------
_resolve_pythonw() {
  # Review: code-reviewer (F6) — returns ONLY the binary name; -3 is a separate arg
  #   passed at the call site, avoiding unquoted word-split on "pyw -3".
  if command -v pythonw3 &>/dev/null; then echo "pythonw3"; return; fi
  if command -v pythonw  &>/dev/null; then echo "pythonw";  return; fi
  if command -v pyw &>/dev/null && pyw -3 --version &>/dev/null 2>&1; then
    echo "pyw"; return
  fi
  echo ""
}

# ------------------------------------------------------------------
# Interpreter-name normalisation: strip leading path, lowercase, drop .exe
# ------------------------------------------------------------------
_interp_base() {
  local name
  name="$(basename "$1")"
  name="${name%.exe}"
  echo "${name,,}"   # lowercase (bash 4+)
}

# ------------------------------------------------------------------
# Main dispatch
# ------------------------------------------------------------------
INTERP_BASE="$(_interp_base "$INTERPRETER")"

if _on_windows; then
  case "$INTERP_BASE" in

    python|python3|python3.*|py)
      # ----------------------------------------------------------------
      # Python on Windows
      # ----------------------------------------------------------------
      if [[ "$STDIN_MODE" == "safe" ]]; then
        # Caller controls stdin → try windowless binary for true suppression.
        PYTHONW="$(_resolve_pythonw)"
        if [[ -n "$PYTHONW" ]]; then
          # Review: code-reviewer (F6) — binary-only from _resolve_pythonw; pass -3 as a
          #   separate arg when the resolved binary is pyw (mirrors resolve-python.sh pattern).
          #   Quoted exec avoids SC2086 word-split; no disable needed.
          if [[ "$PYTHONW" == "pyw" ]]; then
            exec "$PYTHONW" -3 "${ARGS[@]+"${ARGS[@]}"}"
          else
            exec "$PYTHONW" "${ARGS[@]+"${ARGS[@]}"}"
          fi
        fi
        # No windowless variant found — fall through to console binary.
        # Flash will occur; warn so the caller knows.
        echo "spawn-hidden.sh: WARNING: no pythonw/pyw found; console flash will occur for $INTERPRETER" >&2
      else
        # --stdin-mode=pipe: MUST NOT use pythonw — would break harness stdin.
        # No shell-level suppression available.  Pass through transparently.
        # Flash will occur.  True suppression requires machine-belt (Chunk 5)
        # or compiled shim (plan Addendum).
        : # fall through to exec below
      fi
      exec "$INTERPRETER" "${ARGS[@]+"${ARGS[@]}"}"
      ;;

    node|node.exe)
      # ----------------------------------------------------------------
      # Node on Windows
      # ----------------------------------------------------------------
      # There is no "nodew.exe".  windowsHide:true only applies to spawns
      # that Node itself makes via child_process — not to the Node process
      # being spawned from here.  No shell-level suppression available.
      # Flash will occur regardless of --stdin-mode.
      # True suppression requires:
      #   - the spawning PARENT (e.g. Claude Code) to set windowsHide/CREATE_NO_WINDOW, OR
      #   - machine-belt (ConPTY delegation, Chunk 5), OR
      #   - compiled C# shim (plan Addendum).
      if [[ "$STDIN_MODE" == "safe" ]]; then
        echo "spawn-hidden.sh: NOTE: no windowless node variant exists; console flash will occur." >&2
      fi
      exec "$INTERPRETER" "${ARGS[@]+"${ARGS[@]}"}"
      ;;

    pwsh|powershell|powershell.exe|pwsh.exe)
      # ----------------------------------------------------------------
      # PowerShell on Windows
      # ----------------------------------------------------------------
      # -WindowStyle Hidden is create-then-hide — the flash IS the console
      # allocation; Hidden does not prevent it.  No shell-level true
      # suppression exists.  Machine-belt is the correct lever.
      # We pass through transparently; callers should still include
      # -WindowStyle Hidden as the minimum-baseline flag.
      exec "$INTERPRETER" "${ARGS[@]+"${ARGS[@]}"}"
      ;;

    *)
      # Unknown interpreter — pass through.
      exec "$INTERPRETER" "${ARGS[@]+"${ARGS[@]}"}"
      ;;
  esac
else
  # ----------------------------------------------------------------
  # Non-Windows: no console allocation, no suppression needed.
  # exec directly — transparent pass-through.
  # ----------------------------------------------------------------
  exec "$INTERPRETER" "${ARGS[@]+"${ARGS[@]}"}"
fi
