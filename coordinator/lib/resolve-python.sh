#!/usr/bin/env bash
# resolve-python.sh — portable Python resolver for coordinator skills/hooks.
#
# Sets two variables in the caller's scope:
#   PYTHON_BIN  — name of the Python binary to invoke ("python3", "python", "py", or "" if none)
#   PYTHON_ARGS — array of leading args (e.g. ("-3") for the Windows py launcher)
#
# Resolution order: python3 → python → py -3. The `py` branch additionally probes
# `py -3 --version` to confirm a Python 3.x is actually registered (the launcher
# can be present without any 3.x installed — rare but observed on locked-down
# corporate Windows hosts).
#
# Usage:
#   source "${CLAUDE_PLUGIN_ROOT}/lib/resolve-python.sh"
#   [[ -z "$PYTHON_BIN" ]] && { echo "no Python on PATH" >&2; exit 1; }
#   "$PYTHON_BIN" "${PYTHON_ARGS[@]}" -c "..."
#
# Idempotent: callers may source repeatedly; PYTHON_BIN/PYTHON_ARGS are
# overwritten each call.
#
# Callers must not declare PYTHON_BIN or PYTHON_ARGS as readonly — the lib
# resets both unconditionally on each source, and a readonly trap would
# break re-source idempotency.

PYTHON_BIN=""
PYTHON_ARGS=()

# Windows: prefer windowless variants (pythonw.exe / pyw.exe) to avoid
# brief console-window flashes on every hook invocation. python.exe is
# /SUBSYSTEM:CONSOLE and Windows allocates a fresh console when the parent
# (Claude Code GUI / bash without tty) has none. pythonw.exe is identical
# bytecode + /SUBSYSTEM:WINDOWS; piped stdio is inherited normally so
# command-substitution and heredoc input still work.
#
# WARNING — stdin safety caveat (docs/plans/2026-05-29-windows-console-flash-elimination.md § Prior art):
# The pythonw / pyw path is SAFE ONLY for spawns where the caller controls
# stdin (e.g. heredoc, /dev/null, args-only).  Do NOT use this resolver to
# resolve a binary for children whose stdin is a live harness pipe (e.g.
# PreToolUse hooks where Claude Code pipes tool-call JSON on stdin).
# With SUBSYSTEM:WINDOWS, the child may receive a null/invalid stdin handle
# from a console-less parent; a bare except: around sys.stdin reads will
# catch the resulting ValueError/EOFError and silently exit 0 — disabling
# whatever gate the script implements.  Use lib/spawn-hidden.sh with
# --stdin-mode=pipe for those sites (which passes through transparently,
# preserving the live handle, and relies on the machine-belt for suppression).
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*|Windows*)
    if command -v pythonw3 &>/dev/null; then
      PYTHON_BIN="pythonw3"
    elif command -v pythonw &>/dev/null; then
      PYTHON_BIN="pythonw"
    elif command -v pyw &>/dev/null && pyw -3 --version &>/dev/null; then
      PYTHON_BIN="pyw"
      PYTHON_ARGS=("-3")
    fi
    ;;
esac

# Non-Windows, or no windowless variant found: fall back to console binaries.
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
  elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
  elif command -v py &>/dev/null && py -3 --version &>/dev/null; then
    PYTHON_BIN="py"
    PYTHON_ARGS=("-3")
  fi
fi
