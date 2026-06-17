#!/usr/bin/env bash
# ensure-python3-exe-shim.sh — install a python3.exe alongside python.exe on Windows.
#
# Why this exists:
#   Python's `subprocess.run(["python3", ...])` calls Win32 CreateProcess, which
#   does NOT honor PATHEXT and only finds .exe files. The python.org installer
#   ships python.exe and pythonw.exe but NOT python3.exe. So any python child
#   process that re-resolves the interpreter by bare name "python3" fails
#   CreateProcess -> falls through to ShellExecute -> Windows pops the
#   "Select an app to open 'python3'" file-association dialog.
#
#   lib/resolve-python.sh + the python3.cmd shim in templates/bin/ both fix the
#   bash-side and cmd.exe-side resolution paths, but neither helps CreateProcess.
#   A real .exe is the only thing that satisfies CreateProcess's lookup.
#
# What this does (Windows only; no-op elsewhere):
#   1. Locate the python.org install via lib/resolve-python.sh (PYTHON_BIN).
#   2. If python3.exe exists AND matches python.exe (hardlink: implicit; copy:
#      byte-equal), exit 0 (idempotent). If divergent, re-shim.
#   3. Try `mklink /H python3.exe python.exe` (hardlink — same inode, no file
#      data duplication; auto-tracks python.exe updates because they share inode).
#   4. Fall back to a plain copy if hardlink fails (e.g. cross-volume, non-NTFS).
#      Hardlinks do NOT require elevation; mklink /H works in a normal user
#      shell on NTFS. Elevation is only required for /D (symlinks) and /J
#      (junctions), neither of which this script uses.
#
# Idempotent: safe to run repeatedly. Re-running on an existing valid shim is a
# no-op; on a stale copy-fallback shim (python.exe patched but copy not), re-shims.
#
# WSL note: `uname -s` in WSL returns "Linux", so the OS gate exits 0. That's
# correct — WSL processes use Linux namespacing; CreateProcess is not involved.

set -euo pipefail

# Non-Windows (including WSL): no-op, exit 0 silently.
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*|Windows*) : ;;
  *) exit 0 ;;
esac

# Prefer CLAUDE_PLUGIN_ROOT (set by skill/command invocations) over BASH_SOURCE
# derivation — BASH_SOURCE resolves to the symlink path, not the real path, when
# this script is symlinked into a wrapper location.
_plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# shellcheck source=../lib/resolve-python.sh
# shellcheck disable=SC1091
source "${_plugin_root}/lib/resolve-python.sh"

if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "[ensure-python3-exe-shim] no Python interpreter resolved (PYTHON_BIN unset); skipping" >&2
  exit 0
fi

# Skip if resolver fell back to the py/pyw launcher — those are registry-driven
# and don't have a stable on-disk directory we should mutate. Bare names only;
# resolve-python.sh Step 3 does not absolutize the launcher path (see lib lines
# 213-220), so an exact-match guard is sufficient.
case "$PYTHON_BIN" in
  py|pyw)
    echo "[ensure-python3-exe-shim] resolver returned launcher ($PYTHON_BIN); skipping (need a real install dir to shim)" >&2
    exit 0
    ;;
esac

# PYTHON_BIN is a Windows path (resolve-python.sh normalizes via cygpath -w on
# MSYS/Cygwin). Convert to POSIX for filesystem ops here.
if command -v cygpath &>/dev/null; then
  _py_posix="$(cygpath -u "$PYTHON_BIN" 2>/dev/null || printf '%s' "$PYTHON_BIN")"
else
  _py_posix="$(printf '%s' "$PYTHON_BIN" | tr '\\' '/')"
fi

_py_dir="$(dirname "$_py_posix")"
_py_exe_posix="${_py_dir}/python.exe"
_py3_exe_posix="${_py_dir}/python3.exe"

# The resolver may have returned pythonw.exe (windowless-preferred). For the
# shim source we want python.exe — it lives next to pythonw.exe in every
# python.org install.
if [[ ! -f "$_py_exe_posix" ]]; then
  echo "[ensure-python3-exe-shim] python.exe not found at ${_py_exe_posix} (PYTHON_BIN=${PYTHON_BIN}); skipping" >&2
  exit 0
fi

# Pre-shim state guards.
#
# (a) Stale copy after a Python patch upgrade. A hardlink auto-tracks
#     python.exe's inode, so it stays correct. A copy-fallback shim does not —
#     after `python.exe` is replaced by a patch installer, the copy lags. If
#     python3.exe exists but its bytes differ from python.exe, remove and re-shim.
#
# (b) AppX zero-byte reparse-point stub at python3.exe (left over from a Store
#     Python install). `[[ -f $X ]]` is false for reparse-points on MSYS, so
#     execution falls through to mklink which then fails with "file exists".
#     Detect via `-e` && !`-f` and direct the operator to install-substrate.sh's
#     AppX stub cleanup (lines 186-214) before retrying.
if [[ -e "$_py3_exe_posix" && ! -f "$_py3_exe_posix" ]]; then
  echo "[ensure-python3-exe-shim] ${_py3_exe_posix} exists but is not a regular file (likely AppX zero-byte reparse stub)" >&2
  echo "[ensure-python3-exe-shim]   Run install-substrate.sh and accept the orphan-stub deletion prompt, then re-run this script." >&2
  exit 1
fi

if [[ -f "$_py3_exe_posix" ]]; then
  if diff -q "$_py_exe_posix" "$_py3_exe_posix" >/dev/null 2>&1; then
    exit 0
  fi
  echo "[ensure-python3-exe-shim] existing python3.exe diverges from python.exe (stale copy from prior patch?); re-shimming"
  rm -f "$_py3_exe_posix"
fi

# Convert to Windows paths for mklink (a cmd.exe builtin — needs Windows form).
if command -v cygpath &>/dev/null; then
  _py_exe_win="$(cygpath -w "$_py_exe_posix")"
  _py3_exe_win="$(cygpath -w "$_py3_exe_posix")"
else
  _py_exe_win="$_py_exe_posix"
  _py3_exe_win="$_py3_exe_posix"
fi

# mklink /H requires same-volume NTFS. cmd.exe //c double-slash escapes the
# /c switch for MSYS path-mangling (it would otherwise rewrite /c -> C:\).
# Inner \" quotes handle paths with spaces; cmd.exe sees:
#   mklink /H "C:\...\python3.exe" "C:\...\python.exe"
# Capture stderr to a tempfile so any mklink failure is preserved for the
# fallback's error message — don't blindly /dev/null it.
_mklink_err="$(mktemp -t mklink_err.XXXXXX 2>/dev/null || printf '/tmp/mklink_err.%s' "$$")"
trap 'rm -f "$_mklink_err"' EXIT
if cmd.exe //c "mklink /H \"${_py3_exe_win}\" \"${_py_exe_win}\"" >/dev/null 2>"$_mklink_err"; then
  echo "[ensure-python3-exe-shim] hardlinked ${_py3_exe_win} -> python.exe"
  exit 0
fi

# Fallback: plain copy. Works across volumes and on non-NTFS (rare on Windows
# but possible on FAT32 USB installs). Costs ~100KB disk; consumes a separate
# inode but functionally identical for CreateProcess. Note: copies do NOT
# auto-track python.exe patch updates — the pre-shim diff guard above re-shims
# on next run if drift is detected.
if cp "$_py_exe_posix" "$_py3_exe_posix"; then
  echo "[ensure-python3-exe-shim] copied python.exe -> ${_py3_exe_win} (hardlink unavailable; mklink stderr: $(tr -d '\r\n' < "$_mklink_err"))"
  exit 0
fi

echo "[ensure-python3-exe-shim] ERROR: failed to install python3.exe shim at ${_py3_exe_win}" >&2
echo "[ensure-python3-exe-shim]   mklink stderr: $(tr -d '\r\n' < "$_mklink_err")" >&2
echo "[ensure-python3-exe-shim]   Manual fix: cmd.exe /c \"mklink /H \\\"${_py3_exe_win}\\\" \\\"${_py_exe_win}\\\"\"" >&2
exit 1
