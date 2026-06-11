#!/usr/bin/env bash
# install-substrate.sh — coordinator-setup Phase 3 mechanical work.
#
# Lays down ~/.claude/machine-local/ substrate, installs bin/ resolvers
# (machine-local + claude-home families), and runs Windows PATH/AppX
# health checks. Called by coordinator/commands/setup.md Phase 3.
#
# MUST be executed as a subprocess, never sourced. Uses _-prefixed globals
# and `exit` (not `return`); sourcing would pollute the caller's env.
#
# Idempotent: re-runs preserve operator-customized files, emit notices
# instead of overwriting. Fail-loud on missing templates (hard precondition
# for downstream skills).
#
# Env:
#   CLAUDE_PLUGIN_ROOT — required; the coordinator plugin install root.
#   CLAUDE_HOME        — optional; $HOME substitute (see lib/claude-home).
#   COORDINATOR_NON_INTERACTIVE — optional; set to "1" to suppress the AppX
#                                 stub deletion consent prompt. Any other
#                                 value is treated as unset (interactive).

set -euo pipefail

[[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]] || { echo "install-substrate: CLAUDE_PLUGIN_ROOT not set" >&2; exit 1; }

_ml_templates="${CLAUDE_PLUGIN_ROOT}/templates/machine-local"
_ml_bin="${CLAUDE_PLUGIN_ROOT}/templates/bin"
_ch_bin="${CLAUDE_PLUGIN_ROOT}/lib/claude-home"
_setup_src="${CLAUDE_PLUGIN_ROOT}/templates/setup"

# --- Single source of truth for the setup/ percolation file list ---
# F8: pre-source existence check (matches dist/install.sh posture) — under
# `set -euo pipefail` a missing manifest dies with a raw bash error before the
# array-emptiness diagnostic below can fire, so check explicitly first.
_manifest="${CLAUDE_PLUGIN_ROOT}/lib/setup-templates-manifest.sh"
[[ -f "$_manifest" ]] || { echo "install-substrate: setup-templates-manifest.sh not found at ${_manifest}" >&2; exit 1; }
source "$_manifest"

# --- Hard precondition: templates must exist ---
for _required in "$_ml_templates" "$_ml_bin" "$_ch_bin" "$_setup_src"; do
    if [[ ! -d "$_required" ]]; then
        cat >&2 <<EOF
Phase 3 FATAL: required directory not found at $_required.
Cannot lay down machine-local substrate or percolation mechanism, and downstream skills depend on it.
The coordinator plugin install is broken or incomplete. Remediation:
  (a) reinstall the coordinator plugin via the marketplace,
  (b) verify CLAUDE_PLUGIN_ROOT resolves correctly (echo \$CLAUDE_PLUGIN_ROOT),
  (c) if this is a meta-repo dev checkout, confirm the missing dir is present.
EOF
        exit 1
    fi
done
[[ ${#SETUP_TEMPLATE_FILES[@]} -gt 0 ]] || { echo "install-substrate: SETUP_TEMPLATE_FILES is empty — setup-templates-manifest.sh failed to source or is corrupt" >&2; exit 1; }

# --- Resolve install destination (same precedence as claude-home) ---
_install_base="${CLAUDE_HOME:-${HOME}}"
_ml_dst="${_install_base}/.claude/machine-local"
_bin_dst="${_install_base}/.claude/bin"
mkdir -p "$_ml_dst" "$_bin_dst"

# --- Step 2: tracked machine-local files (README, .gitignore, both .example) ---
for _f in README.md .gitignore registry.toml.example registry.local.toml.example; do
    if [[ ! -f "${_ml_dst}/${_f}" ]]; then
        cp "${_ml_templates}/${_f}" "${_ml_dst}/${_f}"
    elif ! diff -q "${_ml_templates}/${_f}" "${_ml_dst}/${_f}" >/dev/null 2>&1; then
        echo "[machine-local] operator-customized ${_f} preserved; template at ${_ml_templates}/${_f} for diff reference"
    fi
done

# --- Step 2b: concern baseline files (copy .example → live name, first-install only) ---
# unreal.toml ships as the schema-only baseline for the `unreal.*` concern namespace.
# Copied only when the target does not exist — never overwrites operator-provisioned state.
# Spec backlink: cross-repo memo 2026-05-21 (unreal-concern-ownership-3-repo plan, AC-1).
if [[ ! -f "${_ml_dst}/unreal.toml" ]]; then
    cp "${_ml_templates}/unreal.toml.example" "${_ml_dst}/unreal.toml"
    echo "[machine-local] installed unreal.toml baseline (schema-only; add values to unreal.local.toml)"
fi

# --- Step 3: bin/ resolvers ---
# machine-local family + python3.cmd come from templates/bin/.
# claude-home family comes from lib/claude-home/ (load-bearing module, not template).
_install_one() {
    local src="$1" dst="$2" exec_bit="$3" warn_prefix="$4"
    if [[ ! -f "$dst" ]]; then
        cp "$src" "$dst"
        if [[ "$exec_bit" == "yes" ]]; then chmod +x "$dst"; fi
    elif diff -q "$src" "$dst" >/dev/null 2>&1; then
        if [[ "$exec_bit" == "yes" ]]; then chmod +x "$dst"; fi
    else
        if [[ "$warn_prefix" == "claude-home" ]]; then
            echo "[claude-home] WARNING: operator-customized $(basename "$dst") preserved, but claude-home is a cross-repo contract surface — customization is anti-doctrine. Diff against $src and restore unless intentional."
        else
            echo "[machine-local] operator-customized $(basename "$dst") preserved; template at $src for diff reference"
        fi
    fi
    # Explicit return 0 — `set -e` traps non-zero from the last evaluated test
    # when the function returns via fall-through. The `if` form above guards
    # the short-circuit, this guarantees clean exit regardless of which branch ran.
    return 0
}

for _f in machine-local _machine_local.py machine-local.cmd python3.cmd; do
    _exec=no
    [[ "$_f" == "machine-local" ]] && _exec=yes
    _install_one "${_ml_bin}/${_f}" "${_bin_dst}/${_f}" "$_exec" "machine-local"
done

for _f in claude-home _claude_home.py claude-home.cmd; do
    _exec=no
    [[ "$_f" == "claude-home" ]] && _exec=yes
    _install_one "${_ch_bin}/${_f}" "${_bin_dst}/${_f}" "$_exec" "claude-home"
done

# --- Step 3c: platform-localize hook ---
# SessionStart hook that auto-generates settings.local.json with correct
# marketplace paths and plugin enablements for this machine. See
# settings-manifest.md for the full architecture.
_install_one "${_ml_bin}/platform-localize.sh" "${_bin_dst}/platform-localize.sh" "yes" "machine-local"

# --- Step 3c-ii: settings-manifest.md ---
# Companion doc for settings.json — documents the portable-vs-machine-specific
# architecture. Placed at ~/.claude/ root for orient-time visibility.
_manifest_src="${CLAUDE_PLUGIN_ROOT}/templates/settings-manifest.md"
_manifest_dst="${_install_base}/.claude/settings-manifest.md"
if [[ -f "$_manifest_src" ]]; then
    _install_one "$_manifest_src" "$_manifest_dst" "no" "machine-local"
fi

# --- Step 3d: percolation mechanism (~/.claude/setup/) ---
# File list is the single source of truth in lib/setup-templates-manifest.sh.
SETUP_DEST="${_install_base}/.claude/setup"
mkdir -p "$SETUP_DEST"
for _f in "${SETUP_TEMPLATE_FILES[@]}"; do
    _exec=no
    for _e in "${SETUP_TEMPLATE_EXEC_FILES[@]}"; do
        [[ "$_f" == "$_e" ]] && _exec=yes && break
    done
    _install_one "$_setup_src/$_f" "$SETUP_DEST/$_f" "$_exec" "machine-local"
done

# percolate-hooks/ doctrine README (subdirectory destination) — also manifest-driven.
# Only the generic README is shipped; per-target hook subdirectories
# (~/.claude/setup/percolate-hooks/<target>/) are operator-authored and
# never templated.
for _hf in "${SETUP_TEMPLATE_HOOK_FILES[@]}"; do
    mkdir -p "$SETUP_DEST/$(dirname "$_hf")"
    _install_one "$_setup_src/$_hf" "$SETUP_DEST/$_hf" "no" "machine-local"
done

# --- Step 3b/3c: Windows-only PATH + AppX Python health ---
# Skip silently on non-Windows.
if [[ "${OSTYPE:-}" != "msys" && "${OSTYPE:-}" != "cygwin" && "${OS:-}" != "Windows_NT" ]]; then
    exit 0
fi

# 3b: ensure the resolved bin dir on Windows user PATH.
# Convert POSIX `_bin_dst` to a Windows path so the PATH comparison/write
# targets the actual install location (honors CLAUDE_HOME, not just USERPROFILE).
_bin_dst_win=$(cygpath -w "${_bin_dst}" 2>/dev/null || echo "")
if [[ -z "$_bin_dst_win" ]]; then
    echo "[setup] WARNING: cygpath unavailable; cannot resolve Windows path for ${_bin_dst}; skipping PATH integration" >&2
else
    # Pass the path via env var so PowerShell sees a clean literal (no bash
    # interpolation into a PS string — defends against quoting injection).
    _already_set=$(BIN_DST_WIN="$_bin_dst_win" powershell.exe -NoProfile -Command \
        "\$p=[Environment]::GetEnvironmentVariable('PATH','User'); \
         \$t=\$env:BIN_DST_WIN; \
         if (\$p -split ';' | Where-Object {\$_ -ieq \$t}) {'yes'} else {'no'}" \
        2>/dev/null | tr -d '\r')
    # Empty string = powershell.exe unavailable or check failed silently
    # (stderr redirected to /dev/null upstream). "yes"/"no" are the only
    # valid values; treat empty as "cannot determine" and skip rather than
    # blindly writing PATH on missing-information.
    if [[ -z "$_already_set" ]]; then
        echo "[setup] WARNING: could not read Windows user PATH (powershell.exe unavailable or check failed); skipping PATH integration" >&2
    elif [[ "$_already_set" != "yes" ]]; then
        BIN_DST_WIN="$_bin_dst_win" powershell.exe -NoProfile -Command \
            "\$p = [Environment]::GetEnvironmentVariable('PATH','User'); \
             [Environment]::SetEnvironmentVariable('PATH', \"\$env:BIN_DST_WIN;\$p\", 'User')" \
            && echo "[setup] added ${_bin_dst_win} to Windows user PATH — restart shells/Claude sessions for it to take effect" \
            || echo "[setup] WARNING: failed to add ${_bin_dst_win} to Windows user PATH" >&2
    fi
fi

# 3c-1: orphan AppX stub detection (zero-byte reparse-points from uninstalled Store Python)
for _stub_name in python.exe python3.exe; do
    _stub_path=$(powershell.exe -NoProfile -Command \
        "\$p = \"\$env:LOCALAPPDATA\Microsoft\WindowsApps\\${_stub_name}\"; \
         if (Test-Path -LiteralPath \$p) { \$i = Get-Item -LiteralPath \$p -Force; \
         if (\$i.Length -eq 0 -and \$i.LinkType -eq 'ReparsePoint' -and -not \$i.Target) { Write-Output \$p } }" \
        2>/dev/null | tr -d '\r')
    if [[ -n "$_stub_path" ]]; then
        echo "[setup] Detected orphan AppX stub: ${_stub_path}"
        echo "[setup]   Zero-byte reparse-point from an uninstalled Store Python package."
        echo "[setup]   Intercepts python3/python invocations via AppX App-Execution-Alias,"
        echo "[setup]   popping the 'Select an app' picker (PATH lookup never runs)."
        echo "[setup]   Regenerates if Store Python is reinstalled."
        if [[ -t 0 ]] && [[ "${COORDINATOR_NON_INTERACTIVE:-}" != "1" ]]; then
            read -r -p "[setup] Delete this orphan stub? [y/N] " _consent
            if [[ "$_consent" =~ ^[Yy] ]]; then
                # Pass path via env var, not shell-interpolated — defends against
                # any shell-special characters in the path (semicolons, quotes,
                # backticks, $(); the path comes from PowerShell output through
                # `tr -d '\r'` and shell-interpolating it directly would be an
                # injection sink).
                STUB_PATH="${_stub_path}" powershell.exe -NoProfile -Command \
                    'Remove-Item -LiteralPath $env:STUB_PATH -Force'
                echo "[setup]   Deleted."
            fi
        else
            echo "[setup]   (non-interactive context: skipping deletion; re-run in interactive shell to clean up)"
        fi
    fi
done

# 3c-2: store-alias-on-PATH warning
_py_resolved=$(powershell.exe -NoProfile -Command \
    "\$c = Get-Command python3 -ErrorAction SilentlyContinue; \
     if (-not \$c) { \$c = Get-Command python -ErrorAction SilentlyContinue }; \
     if (\$c) { Write-Output \$c.Source }" 2>/dev/null | tr -d '\r')
case "$_py_resolved" in
    *WindowsApps*)
        echo "[setup] WARNING: python/python3 resolves under WindowsApps: ${_py_resolved}"
        echo "[setup]   Install Python from python.org OR disable App Execution Aliases via"
        echo "[setup]   Settings → Apps → Advanced app settings → App execution aliases."
        ;;
esac

# 3c-3: no-Python-at-all detection
_have_py=$(powershell.exe -NoProfile -Command \
    "\$p = Get-Command py -ErrorAction SilentlyContinue; \
     if (\$p) { Write-Output 'yes' } else { Write-Output 'no' }" 2>/dev/null | tr -d '\r')
if [[ "$_have_py" != "yes" && -z "$_py_resolved" ]]; then
    echo "[setup] WARNING: neither py.exe nor python/python3 found."
    echo "[setup]   Install Python 3 from https://www.python.org/downloads/windows/ —"
    echo "[setup]   the installer ships py.exe by default. Without it, python3.cmd has nothing to call."
fi
