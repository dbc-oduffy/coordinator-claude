#!/usr/bin/env bash
# resolve-python.sh — portable Python resolver for coordinator skills/hooks.
#
# Sets two variables in the caller's scope:
#   PYTHON_BIN  — absolute path to the Python binary (Windows: python.org install
#                 preferred over Store install; falls back to bare "py" launcher
#                 only when neither is on disk; "" if no interpreter found)
#   PYTHON_ARGS — array of leading args (e.g. ("-3") for the Windows py launcher)
#
# Windows resolution order:
#   1. Direct probe of python.org install dirs (LOCALAPPDATA\Programs\Python\Python3*,
#      C:\Program Files\Python3*, C:\Python3*), windowless variant preferred.
#   2. PATH resolution via `command -v`, REJECTING any match under …\WindowsApps\…
#      (the sandboxed Microsoft Store Python install — see _resolve_python_is_store).
#   3. The `py` / `pyw` launcher with `-3`, validated by `--version`.
#
# Non-Windows resolution order: python3 → python, absolutized via `command -v`.
#
# PATH is seeded with the resolved interpreter's directory so child processes
# that re-resolve by bare name (subprocess.run(["python3"]), uv, pip, venv shims)
# find the same install instead of tripping Windows ShellExecute file-association
# fallback ("Select an app to open 'python3'" dialog).
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
#
# Note: four private _resolve_python_* helper functions remain in scope after
# sourcing; treat them as implementation details.

PYTHON_BIN=""
PYTHON_ARGS=()

# Resolve a bare-name interpreter to its absolute path (via `command -v`) and
# prepend its directory to PATH for the caller's process tree. Child processes
# (subprocess.run(["python3"]), uv, pip, venv shims, anything that re-resolves
# the interpreter by name) then find a working binary instead of falling through
# to Windows ShellExecute and triggering the "Select an app to open 'python3'"
# file-association dialog — observed 2026-06-16 when agent shells had a PATH
# without %LOCALAPPDATA%\Microsoft\WindowsApps and a child process tried to
# launch bare `python3`.
_resolve_python_absolutize() {
  local name="$1" path
  path="$(command -v "$name" 2>/dev/null)" || return 1
  # On MSYS/Cygwin, `command -v` may emit a POSIX path; cygpath converts to
  # Windows form when available so callers can pass the result to native tools.
  # cygpath -w is idempotent on already-Windows paths; the printf fallback
  # preserves the POSIX path as-is when cygpath is absent.
  if command -v cygpath &>/dev/null; then
    path="$(cygpath -w "$path" 2>/dev/null || printf '%s' "$path")"
  fi
  printf '%s' "$path"
}

_resolve_python_prepend_path() {
  local bin_path="$1" bin_dir
  [[ -z "$bin_path" ]] && return 0
  if command -v cygpath &>/dev/null; then
    bin_dir="$(dirname "$(cygpath -u "$bin_path" 2>/dev/null || printf '%s' "$bin_path")")"
  else
    # Normalize backslashes before dirname so Windows-style paths (C:\...\pythonw.exe)
    # don't produce "C:" — dirname treats \ as a literal character, not a separator.
    bin_dir="$(dirname "$(printf '%s' "$bin_path" | tr '\\' '/')")"
  fi
  case ":$PATH:" in
    *":$bin_dir:"*) : ;;
    *) export PATH="$bin_dir:$PATH" ;;
  esac
}

# Reject the Microsoft Store Python install. The Store package's symlinks live
# under %LOCALAPPDATA%\Microsoft\WindowsApps\ and resolve into
# C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.*\. It's
# sandboxed: filesystem and registry writes are redirected to per-package
# virtualized locations, `pip --user` lands in a hidden tree, and package
# permissions are inconsistent. Always prefer the python.org installer.
_resolve_python_is_store() {
  case "$1" in
    *[Ww]indows[Aa]pps*) return 0 ;;
    *) return 1 ;;
  esac
}

# Probe known python.org install locations in descending version order, looking
# for a windowless interpreter first (to keep the console-flash fix) then the
# console binary. Returns the first absolute path found, or empty.
_resolve_python_pyorg_search() {
  local prefer_windowless="$1" base candidates=() dir hit
  # Per-user installs (python.org default).
  if [[ -n "$LOCALAPPDATA" ]]; then
    base="$(cygpath -u "$LOCALAPPDATA" 2>/dev/null || printf '%s' "$LOCALAPPDATA")"
    candidates+=("$base/Programs/Python")
  fi
  # System-wide installs. Use cygpath to compute the correct POSIX form of
  # C:\Program Files\... so this works under MSYS (/c/), Cygwin (/cygdrive/c/),
  # and WSL (/mnt/c/). Fall back to the MSYS form if cygpath is absent.
  # Review: code-reviewer — /c/... paths fail under Cygwin (uses /cygdrive/c/)
  # and WSL (uses /mnt/c/); cygpath normalizes the mount point at runtime.
  candidates+=("$(cygpath -u 'C:\Program Files\Python313' 2>/dev/null || echo '/c/Program Files/Python313')")
  candidates+=("$(cygpath -u 'C:\Program Files\Python312' 2>/dev/null || echo '/c/Program Files/Python312')")
  candidates+=("$(cygpath -u 'C:\Program Files\Python311' 2>/dev/null || echo '/c/Program Files/Python311')")
  candidates+=("$(cygpath -u 'C:\Program Files\Python310' 2>/dev/null || echo '/c/Program Files/Python310')")
  candidates+=("$(cygpath -u 'C:\Python313' 2>/dev/null || echo '/c/Python313')")
  candidates+=("$(cygpath -u 'C:\Python312' 2>/dev/null || echo '/c/Python312')")
  candidates+=("$(cygpath -u 'C:\Python311' 2>/dev/null || echo '/c/Python311')")
  candidates+=("$(cygpath -u 'C:\Python310' 2>/dev/null || echo '/c/Python310')")

  # For per-user "Programs/Python" parent, enumerate Python3.x children newest-first.
  local expanded=()
  for dir in "${candidates[@]}"; do
    if [[ "$dir" == */Programs/Python ]]; then
      # shellcheck disable=SC2012
      while IFS= read -r child; do
        [[ -n "$child" ]] && expanded+=("$child")
      # sort -r gives descending lex order; this is correct only for three-digit
      # minor versions (3.10+). Python 3.9 and below would sort incorrectly here
      # (3.9 > 3.10 lexicographically). sort -rV would fix it but is GNU-only
      # and banned by DR-148.
      done < <(ls -1d "$dir"/Python3* 2>/dev/null | sort -r)
    else
      expanded+=("$dir")
    fi
  done

  local probes=()
  if [[ "$prefer_windowless" == "1" ]]; then
    probes=("pythonw.exe" "python.exe")
  else
    probes=("python.exe" "pythonw.exe")
  fi

  for dir in "${expanded[@]}"; do
    for hit in "${probes[@]}"; do
      if [[ -x "$dir/$hit" ]]; then
        if command -v cygpath &>/dev/null; then
          # Guard against cygpath -w emitting empty + exit 0, which would cause
          # the caller to receive an empty PYTHON_BIN and silently skip this hit.
          # Review: code-reviewer — cygpath -w may emit empty + exit 0 on some
          # paths; check non-empty before returning.
          local _wpath
          _wpath="$(cygpath -w "$dir/$hit" 2>/dev/null)"
          [[ -n "$_wpath" ]] && { printf '%s' "$_wpath"; return 0; }
        else
          printf '%s' "$dir/$hit" && return 0
        fi
      fi
    done
  done
  return 1
}

# ---------------------------------------------------------------------------
# Pinned-interpreter tier (OS-agnostic, runs before OS detection).
#
# Resolution order:
#   1. COORDINATOR_PYTHON env var (non-empty)
#   2. machine-local get coordinator.python (if machine-local CLI is available)
#
# A found pin is VALIDATED — a file that exists but cannot run
# `python -c 'import sys'` (e.g. a dangling venv shim) is a hard failure:
# print an error and return 1.  Silently falling through to bare python3 when
# a pin is broken masks the exact failure this guard exists to catch.
#
# On success: PYTHON_BIN is set and PYTHON_ARGS is reset to () so a stale
# ("-3") from a prior run cannot leak onto an absolute-path pin.
# On no-pin-found: fall through to the OS-detection block below.
#
# Spec backlink: docs/plans/2026-06-20-whoami-durable-install-surface.md § C1
# ---------------------------------------------------------------------------
_resolve_python_pin_candidate=""

# 1. Env var override.
if [[ -n "${COORDINATOR_PYTHON:-}" ]]; then
  _resolve_python_pin_candidate="$COORDINATOR_PYTHON"
fi

# 2. machine-local registry (only if env var not set).
if [[ -z "$_resolve_python_pin_candidate" ]]; then
  _ml_cli=""
  if command -v machine-local &>/dev/null; then
    _ml_cli="machine-local"
  else
    # Lib-relative fallback: <lib-dir>/../bin/machine-local
    _ml_librel="$(dirname "${BASH_SOURCE[0]}")/../bin/machine-local"
    if [[ -x "$_ml_librel" ]]; then
      _ml_cli="$_ml_librel"
    fi
  fi
  unset _ml_librel

  if [[ -n "$_ml_cli" ]]; then
    _ml_pin="$("$_ml_cli" get coordinator.python 2>/dev/null || true)"
    if [[ -n "$_ml_pin" ]]; then
      _resolve_python_pin_candidate="$_ml_pin"
    fi
    unset _ml_pin
  fi
  unset _ml_cli
fi

# Validate and apply any pin found.
if [[ -n "$_resolve_python_pin_candidate" ]]; then
  if "$_resolve_python_pin_candidate" -c 'import sys' >/dev/null 2>&1; then
    PYTHON_BIN="$_resolve_python_pin_candidate"
    PYTHON_ARGS=()
  else
    echo "resolve-python: pinned interpreter '$_resolve_python_pin_candidate' is invalid (exists but cannot run 'import sys'). Re-run /coordinator:install to rebuild the coordinator venv." >&2
    unset _resolve_python_pin_candidate
    return 1
  fi
fi
unset _resolve_python_pin_candidate

# ---------------------------------------------------------------------------
# OS-detection fallback — runs only when no pin was applied above.
#
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
if [[ -z "$PYTHON_BIN" ]]; then
  _is_windows=0
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*|Windows*) _is_windows=1 ;;
  esac

  if [[ "$_is_windows" == "1" ]]; then
    # Step 1 — direct probe of the python.org installer locations. This bypasses
    # PATH entirely (and therefore the Store-Python symlink farm in
    # %LOCALAPPDATA%\Microsoft\WindowsApps\), preferring the windowless variant
    # to keep console-flash suppression.
    _resolved="$(_resolve_python_pyorg_search 1 || true)"
    if [[ -n "$_resolved" ]]; then
      PYTHON_BIN="$_resolved"
    fi
    unset _resolved

    # Step 2 — fall back to PATH resolution, but reject any match under WindowsApps.
    if [[ -z "$PYTHON_BIN" ]]; then
      # pythonw3 is not a real binary on any python.org Windows distribution.
      # Review: code-reviewer — pythonw3 does not exist; removed from probe list.
      for _name in pythonw python3 python; do
        if command -v "$_name" &>/dev/null; then
          _candidate="$(_resolve_python_absolutize "$_name" || true)"
          if [[ -n "$_candidate" ]] && ! _resolve_python_is_store "$_candidate"; then
            PYTHON_BIN="$_candidate"
            break
          fi
        fi
      done
      unset _name _candidate
    fi

    # Step 3 — the `py` / `pyw` launcher. Trust it: it reads PEP 514 registry
    # entries and selects an installed 3.x — typically the python.org install
    # if one exists, not the Store package.
    if [[ -z "$PYTHON_BIN" ]]; then
      if command -v pyw &>/dev/null && pyw -3 --version &>/dev/null; then
        PYTHON_BIN="pyw"
        PYTHON_ARGS=("-3")
      elif command -v py &>/dev/null && py -3 --version &>/dev/null; then
        PYTHON_BIN="py"
        PYTHON_ARGS=("-3")
      fi
    fi
  else
    # Non-Windows — bare-name PATH resolution, then absolutize.
    if command -v python3 &>/dev/null; then
      PYTHON_BIN="python3"
    elif command -v python &>/dev/null; then
      PYTHON_BIN="python"
    fi
    if [[ -n "$PYTHON_BIN" ]]; then
      _resolved="$(_resolve_python_absolutize "$PYTHON_BIN" || true)" # verify-no-console-flash: allow — string literal, not an interpreter spawn; $PYTHON_BIN is an arg to a shell function
      [[ -n "$_resolved" ]] && PYTHON_BIN="$_resolved"
      unset _resolved
    fi
  fi
  unset _is_windows
fi  # end: no-pin fallback block

# Seed PATH so child processes that re-resolve the interpreter by name (Python
# subprocess.run(["python3"]), uv, pip, venv shims) find a working binary in
# the same install instead of falling through to the Windows ShellExecute
# file-association dialog ("Select an app to open 'python3'", observed
# 2026-06-16 on agent shells without %LOCALAPPDATA%\Microsoft\WindowsApps on
# PATH).  Skip for the py/pyw launcher — those are intentionally bare-name.
#
# The py/pyw launchers are excluded from PATH seeding because they resolve
# through the Windows registry (PEP 514), not PATH. Seeding their directory
# would prepend C:\Windows\System32, which is already present and adds no
# value. Review: code-reviewer — guard lacks rationale comment; added.
if [[ -n "$PYTHON_BIN" && "$PYTHON_BIN" != "py" && "$PYTHON_BIN" != "pyw" ]]; then
  _resolve_python_prepend_path "$PYTHON_BIN" # verify-no-console-flash: allow — string literal, not an interpreter spawn; $PYTHON_BIN is an arg to a shell function
fi
# PYTHON_ARGS is intentionally NOT exported — callers must source this lib to
# get both variables. Using exported PYTHON_BIN alone (without PYTHON_ARGS) is
# unsafe when the launcher fallback fires: pyw without -3 may select Python 2
# if a Python 2 interpreter is registered in the Windows registry (PEP 514).
# Review: code-reviewer — PYTHON_ARGS not-exported asymmetry undocumented.
export PYTHON_BIN
