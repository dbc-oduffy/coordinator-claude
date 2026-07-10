#!/usr/bin/env bash
# detect-hardware.sh — cross-platform hardware audit for the machine-local registry.
#
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md §C4
# Purpose: detect CPU cores, RAM, and (best-effort) GPU/VRAM, then persist the
# values into hardware.local.toml via the --concern writer in the machine-local
# CLI. Idempotent: re-run re-audits and upserts without losing other keys.
#
# Platforms:
#   Linux   — /proc/cpuinfo (nproc), /proc/meminfo
#   macOS   — sysctl hw.ncpu, hw.memsize
#   Windows — PowerShell Get-CimInstance Win32_ComputerSystem (NOT deprecated wmic)
#
# GPU/VRAM detection is best-effort and non-blocking: if the probe fails or the
# tool is unavailable, the key is simply not written — no error is emitted.
#
# Fail-loud policy: if a required probe (cores, RAM) cannot resolve a value, the
# script exits non-zero with a specific remediation message. Never writes a
# placeholder or a wrong number.
#
# Prerequisites: `machine-local` must be on PATH (installed by install-substrate.sh
# before this script is called). MACHINE_LOCAL_REGISTRY_DIR may override the
# default registry location for testing.
#
# Usage: bash detect-hardware.sh
#
# Negative-spec: does NOT use deprecated wmic on Windows (Get-CimInstance only).
# Negative-spec: does NOT write to registry.local.toml — --concern hardware only.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve machine-local binary
# ---------------------------------------------------------------------------
if command -v machine-local >/dev/null 2>&1; then
    _ml=machine-local
elif [[ -n "${CLAUDE_HOME:-}" ]] && [[ -x "${CLAUDE_HOME}/.claude/bin/machine-local" ]]; then
    _ml="${CLAUDE_HOME}/.claude/bin/machine-local"
elif [[ -x "${HOME}/.claude/bin/machine-local" ]]; then
    _ml="${HOME}/.claude/bin/machine-local"
else
    echo "detect-hardware: machine-local not found on PATH or at ~/.claude/bin/machine-local" >&2
    echo "  Remediation: run install-substrate.sh first, or ensure ~/.claude/bin is on PATH." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_os_type="${OSTYPE:-}"
_is_windows=0
_is_macos=0
_is_linux=0

if [[ "$_os_type" == "msys" || "$_os_type" == "cygwin" || "${OS:-}" == "Windows_NT" ]]; then
    _is_windows=1
elif [[ "$_os_type" == darwin* ]]; then
    _is_macos=1
else
    _is_linux=1
fi

# ---------------------------------------------------------------------------
# Detect CPU cores
# ---------------------------------------------------------------------------
_cores=""

if [[ "$_is_windows" -eq 1 ]]; then
    if command -v powershell.exe >/dev/null 2>&1; then
        _cores=$(powershell.exe -NoProfile -WindowStyle Hidden -Command \
            '(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors' \
            2>/dev/null | tr -d '\r\n ')
    elif [[ -n "${NUMBER_OF_PROCESSORS:-}" ]]; then
        _cores="$NUMBER_OF_PROCESSORS"
    fi
elif [[ "$_is_macos" -eq 1 ]]; then
    if command -v sysctl >/dev/null 2>&1; then
        _cores=$(sysctl -n hw.ncpu 2>/dev/null || echo "")
    fi
else
    # Linux
    if command -v nproc >/dev/null 2>&1; then
        _cores=$(nproc 2>/dev/null || echo "")
    elif [[ -f /proc/cpuinfo ]]; then
        _cores=$(grep -c '^processor' /proc/cpuinfo 2>/dev/null || echo "")
    fi
fi

if [[ -z "$_cores" ]] || ! [[ "$_cores" =~ ^[0-9]+$ ]]; then
    echo "detect-hardware: could not determine CPU core count." >&2
    echo "  Remediation: set hardware.cores manually:" >&2
    echo "    machine-local set --concern hardware hardware.cores <n>" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Detect RAM (GB, rounded to nearest integer)
# ---------------------------------------------------------------------------
_ram_bytes=""
_ram_gb=""

if [[ "$_is_windows" -eq 1 ]]; then
    if command -v powershell.exe >/dev/null 2>&1; then
        _ram_bytes=$(powershell.exe -NoProfile -WindowStyle Hidden -Command \
            '(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory' \
            2>/dev/null | tr -d '\r\n ')
    fi
elif [[ "$_is_macos" -eq 1 ]]; then
    if command -v sysctl >/dev/null 2>&1; then
        _ram_bytes=$(sysctl -n hw.memsize 2>/dev/null || echo "")
    fi
else
    # Linux: /proc/meminfo reports kB
    if [[ -f /proc/meminfo ]]; then
        _ram_kb=$(grep '^MemTotal:' /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "")
        if [[ -n "$_ram_kb" ]] && [[ "$_ram_kb" =~ ^[0-9]+$ ]]; then
            _ram_bytes=$(( _ram_kb * 1024 ))
        fi
    fi
fi

if [[ -n "$_ram_bytes" ]] && [[ "$_ram_bytes" =~ ^[0-9]+$ ]]; then
    # Round to nearest GB: (bytes + 536870912) / 1073741824
    _ram_gb=$(( (_ram_bytes + 536870912) / 1073741824 ))
fi

if [[ -z "$_ram_gb" ]] || ! [[ "$_ram_gb" =~ ^[0-9]+$ ]]; then
    echo "detect-hardware: could not determine total RAM." >&2
    echo "  Remediation: set hardware.ram_gb manually:" >&2
    echo "    machine-local set --concern hardware hardware.ram_gb <n>" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Detect GPU / VRAM (best-effort, non-blocking)
# ---------------------------------------------------------------------------
_gpu=""
_vram_gb=""

if [[ "$_is_windows" -eq 1 ]] && command -v powershell.exe >/dev/null 2>&1; then
    _gpu=$(powershell.exe -NoProfile -WindowStyle Hidden -Command \
        'try { (Get-CimInstance Win32_VideoController | Select-Object -First 1).Name } catch {}' \
        2>/dev/null | tr -d '\r' | tr -s ' ' | head -1 || echo "")
    _vram_bytes=$(powershell.exe -NoProfile -WindowStyle Hidden -Command \
        'try { (Get-CimInstance Win32_VideoController | Select-Object -First 1).AdapterRAM } catch {}' \
        2>/dev/null | tr -d '\r\n ' || echo "")
    if [[ -n "$_vram_bytes" ]] && [[ "$_vram_bytes" =~ ^[0-9]+$ ]] && [[ "$_vram_bytes" -gt 0 ]]; then
        _vram_gb=$(( (_vram_bytes + 536870912) / 1073741824 ))
    fi
elif [[ "$_is_macos" -eq 1 ]]; then
    if command -v system_profiler >/dev/null 2>&1; then
        _gpu=$(system_profiler SPDisplaysDataType 2>/dev/null \
            | awk -F': ' '/Chipset Model:/{print $2; exit}' || echo "") # Review: reviewer — $NF printed only last word ("Pro"); -F': ' captures full value after label
    fi
elif [[ "$_is_linux" -eq 1 ]]; then
    if command -v lspci >/dev/null 2>&1; then
        _gpu=$(lspci 2>/dev/null | grep -i 'vga\|3d\|display' | head -1 \
            | sed 's/.*: //' | sed 's/ (.*//' || echo "")
    fi
fi

# ---------------------------------------------------------------------------
# Persist values via --concern writer
# ---------------------------------------------------------------------------
echo "[detect-hardware] cores=${_cores} ram_gb=${_ram_gb}"
"$_ml" set --concern hardware hardware.cores "${_cores}"
"$_ml" set --concern hardware hardware.ram_gb "${_ram_gb}"

if [[ -n "$_gpu" ]]; then
    echo "[detect-hardware] gpu=${_gpu}"
    "$_ml" set --concern hardware hardware.gpu "${_gpu}" || true
fi

if [[ -n "$_vram_gb" ]] && [[ "$_vram_gb" =~ ^[0-9]+$ ]] && [[ "$_vram_gb" -gt 0 ]]; then
    echo "[detect-hardware] vram_gb=${_vram_gb}"
    "$_ml" set --concern hardware hardware.vram_gb "${_vram_gb}" || true
fi

echo "[detect-hardware] hardware audit complete — values in hardware.local.toml"
