#!/usr/bin/env bash
# bin/probe-memory-headroom.sh — Best-effort cross-platform RAM/VRAM headroom probe.
#
# Purpose: the load-bearing resource for a fan-out wave is memory commit (RAM/VRAM),
# NOT CPU core count. The large-wave NOTE in bin/fan-out-dispatch.sh historically used a
# core-count proxy (3× logical cores); this probe is its memory-commit-aware successor —
# it reads what actually degrades the machine (available RAM and free GPU VRAM) so the
# fan-out advisory can surface live headroom and fire on a tight machine regardless of
# wave size. See docs/plans/2026-05-30-organic-ramp-concurrency-doctrine.md §111-114.
#
# Design — best-effort, graceful degradation: this is a SOFT advisory input. Every probe
# leg is wrapped so an unsupported platform, a missing tool (no nvidia GPU, no PowerShell),
# a wedged driver, or a parse miss yields `unknown` for that field rather than aborting.
# The caller treats `unknown` as "no signal on this axis" and falls back to the cores proxy.
# Exit is always 0 except a usage error; absence of signal is communicated in the VALUES,
# never the exit code. External tool calls are wall-clock bounded (see _bounded) so a stuck
# nvidia-smi or a slow PowerShell cold-start cannot stall the caller's dispatch. On a host
# lacking both `timeout` and `gtimeout`, cs_timeout uses a background-kill approach (Branch B)
# to bound the call; the fan-out caller's 10 s outer cap (fan-out-dispatch.sh) is defense-in-depth backstop.
# Review: code-reviewer S3 F1 — stale docblock: Branch B now bounds on macOS; fan-out cap is backstop only.
#
# NOTE — sibling implementation: whoami/coordinator_whoami/host_probes.py::_probe_memory is a
# SEPARATE RAM probe consumed by the machine-identity / doctor tooling (Python, psutil-shaped).
# This shell probe is authoritative for the fan-out path only. They are intentionally not
# unified (different languages, different consumers, both soft-advisory) — keep this comment
# and that one cross-referenced if either's contract changes.
#
# Output (stdout) — stable key=value lines, always all four keys, value is an integer or
# the literal `unknown`:
#   ram_available_mb=<int|unknown>   # MemAvailable (Linux) / FreePhysicalMemory (Win) / free+inactive+spec (mac)
#   ram_total_mb=<int|unknown>
#   vram_free_mb=<int|unknown>       # summed across NVIDIA GPUs; unknown if no nvidia-smi
#   vram_total_mb=<int|unknown>
#
# Usage:
#   bash bin/probe-memory-headroom.sh            # key=value lines (machine-parseable)
#   bash bin/probe-memory-headroom.sh --human    # one human-readable sentence
#
# Platform coverage: Linux/WSL (/proc/meminfo), Windows git-bash/MSYS (PowerShell CIM),
# macOS (sysctl + vm_stat). VRAM is NVIDIA-only (nvidia-smi) on any platform; AMD/Intel
# GPUs report `unknown` (no portable query) — deliberately, not a bug.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source portable timeout primitive from the shared watchdog lib. The lib is
# functions-only and idempotent (guarded against double-source) — sourcing it
# here does NOT trigger any probe execution. Safe even when probe-memory-headroom.sh
# is itself sourced by a caller (no top-level executable statements in the lib).
# Spec backlink: docs/plans/2026-06-27-coordinator-watchdog.md
# shellcheck source=../lib/coordinator-watchdog.sh
source "${SCRIPT_DIR}/../lib/coordinator-watchdog.sh"

RAM_AVAIL_MB="unknown"
RAM_TOTAL_MB="unknown"
VRAM_FREE_MB="unknown"
VRAM_TOTAL_MB="unknown"

# Wall-clock-bound an external command via the shared cs_timeout primitive.
# cs_timeout handles timeout/gtimeout/background-kill fallback portably; on a host
# lacking both `timeout` and `gtimeout` it uses a background-kill approach rather
# than running unbounded — a stricter guarantee than the prior hand-rolled fallback.
# The fan-out caller's 10 s outer cap (fan-out-dispatch.sh) remains the backstop.
# NOTE — stderr suppression: callers supply 2>/dev/null on their _bounded invocations;
# this wrapper does NOT apply it internally (preserves cs_timeout diagnostic output).
# Review: code-reviewer S3 F4 — document caller-supplied stderr suppression convention.
_bounded() {
    local secs="$1"; shift
    cs_timeout "$secs" -- "$@"
}

# Render an MB integer as a compact human magnitude: "≈N GB" at ≥1 GB, "≈N MB" below
# (integer GB truncation would print "≈0 GB" for a memory-starved machine — exactly the
# case the headroom-tight signal exists to surface).
_fmt_mb() {
    local mb="$1"
    if [[ "$mb" -ge 1024 ]]; then
        echo "≈$(( mb / 1024 )) GB"
    else
        echo "≈${mb} MB"
    fi
}

# --- RAM: Linux / WSL — /proc/meminfo is authoritative and cheap -------------
_ram_from_proc() {
    [[ -r /proc/meminfo ]] || return 1
    local avail_kb total_kb
    # MemAvailable is the kernel's reclaim-aware estimate; fall back to MemFree on
    # pre-3.14 kernels that lack it (conservative — undercounts true headroom).
    avail_kb="$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo)"
    [[ -n "$avail_kb" ]] || avail_kb="$(awk '/^MemFree:/ {print $2; exit}' /proc/meminfo)"
    total_kb="$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo)"
    [[ "$avail_kb" =~ ^[0-9]+$ ]] || return 1
    RAM_AVAIL_MB=$(( avail_kb / 1024 ))
    if [[ "$total_kb" =~ ^[0-9]+$ ]]; then RAM_TOTAL_MB=$(( total_kb / 1024 )); fi
    return 0
}

# --- RAM: Windows git-bash/MSYS — PowerShell CIM (wmic is deprecated on Win11) ---
_ram_from_windows() {
    command -v powershell.exe >/dev/null 2>&1 || return 1
    local out="" free_kb="" total_kb=""
    # FreePhysicalMemory and TotalVisibleMemorySize are reported in KB. FreePhysicalMemory
    # is "free" not "available" (excludes reclaimable cache) — conservative for a headroom
    # floor, which is the safe direction for a soft nudge. Bounded against PowerShell cold-start.
    out="$(_bounded 5 powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -Command \
        '$o=Get-CimInstance Win32_OperatingSystem; "{0} {1}" -f $o.FreePhysicalMemory,$o.TotalVisibleMemorySize' \
        2>/dev/null)" || return 1
    out="${out//$'\r'/}"
    read -r free_kb total_kb <<< "$out"
    [[ "$free_kb" =~ ^[0-9]+$ ]] || return 1
    RAM_AVAIL_MB=$(( free_kb / 1024 ))
    if [[ "$total_kb" =~ ^[0-9]+$ ]]; then RAM_TOTAL_MB=$(( total_kb / 1024 )); fi
    return 0
}

# --- RAM: macOS — sysctl for total, vm_stat pages for available --------------
_ram_from_macos() {
    command -v sysctl >/dev/null 2>&1 || return 1
    command -v vm_stat >/dev/null 2>&1 || return 1
    local total_bytes pagesize stats free inactive spec avail_pages
    total_bytes="$(sysctl -n hw.memsize 2>/dev/null)" || return 1
    pagesize="$(sysctl -n hw.pagesize 2>/dev/null)" || pagesize=4096
    [[ "$pagesize" =~ ^[0-9]+$ ]] || pagesize=4096
    stats="$(vm_stat 2>/dev/null)" || return 1
    # Available ≈ free + inactive + speculative pages (reclaimable without paging out).
    # vm_stat sample line: "Pages free:                          123456."  → $3 holds the
    # count (trailing period stripped). Patterns anchored to ^Pages to avoid stray matches.
    free="$(printf '%s\n' "$stats"     | awk '/^Pages free/ {gsub(/\./,"",$3); print $3; exit}')"
    inactive="$(printf '%s\n' "$stats" | awk '/^Pages inactive/ {gsub(/\./,"",$3); print $3; exit}')"
    spec="$(printf '%s\n' "$stats"     | awk '/^Pages speculative/ {gsub(/\./,"",$3); print $3; exit}')"
    [[ "$free" =~ ^[0-9]+$ ]] || return 1
    [[ "$inactive" =~ ^[0-9]+$ ]] || inactive=0
    [[ "$spec" =~ ^[0-9]+$ ]] || spec=0
    avail_pages=$(( free + inactive + spec ))
    # Divide before multiplying: avail_pages * pagesize can reach ~32e9 on a large-RAM box,
    # which would wrap on any shell using 32-bit integer arithmetic. (pagesize/1024) is exact
    # for all real Apple page sizes (4096, 16384).
    RAM_AVAIL_MB=$(( (avail_pages / 1024) * (pagesize / 1024) ))
    # Set total only after available succeeds — keep the leg's failure mode all-or-nothing,
    # matching the Linux/Windows legs (never a real total beside an unknown available).
    if [[ "$total_bytes" =~ ^[0-9]+$ ]]; then RAM_TOTAL_MB=$(( total_bytes / 1024 / 1024 )); fi
    return 0
}

# --- VRAM: NVIDIA only, any platform — sum free/total across GPUs ------------
_vram_from_nvidia() {
    command -v nvidia-smi >/dev/null 2>&1 || return 1
    local out f t free_sum=0 total_sum=0 saw_free=0 saw_total=0
    # Bounded: a wedged NVIDIA driver makes nvidia-smi hang indefinitely (known issue).
    out="$(_bounded 3 nvidia-smi --query-gpu=memory.free,memory.total --format=csv,noheader,nounits 2>/dev/null)" || return 1
    out="${out//$'\r'/}"
    while IFS=',' read -r f t; do
        f="${f// /}"; t="${t// /}"
        if [[ "$f" =~ ^[0-9]+$ ]]; then free_sum=$(( free_sum + f )); saw_free=1; fi
        if [[ "$t" =~ ^[0-9]+$ ]]; then total_sum=$(( total_sum + t )); saw_total=1; fi
    done <<< "$out"
    [[ "$saw_free" -eq 1 ]] || return 1
    VRAM_FREE_MB="$free_sum"
    # Only report a total if at least one GPU gave a numeric one — never a misleading 0.
    if [[ "$saw_total" -eq 1 ]]; then VRAM_TOTAL_MB="$total_sum"; fi
    return 0
}

case "$(uname -s 2>/dev/null || echo unknown)" in
    Linux*)               _ram_from_proc    || true ;;
    Darwin*)              _ram_from_macos   || true ;;
    MINGW*|MSYS*|CYGWIN*) _ram_from_windows || true ;;
    *)                    : ;;
esac

_vram_from_nvidia || true

# --- Output -----------------------------------------------------------------
if [[ "${1:-}" == "--human" ]]; then
    if [[ -n "${2:-}" ]]; then
        echo "usage: probe-memory-headroom.sh [--human]" >&2
        exit 2
    fi
    # Human mode reports only the available/free fields (the load-bearing ones); totals
    # are in key=value mode for callers that want them.
    parts=()
    if [[ "$RAM_AVAIL_MB" =~ ^[0-9]+$ ]]; then parts+=("RAM free $(_fmt_mb "$RAM_AVAIL_MB")"); fi
    if [[ "$VRAM_FREE_MB" =~ ^[0-9]+$ ]]; then parts+=("VRAM free $(_fmt_mb "$VRAM_FREE_MB")"); fi
    if [[ "${#parts[@]}" -eq 0 ]]; then
        echo "memory headroom: unavailable on this platform"
    else
        ( IFS=', '; echo "memory headroom: ${parts[*]}" )
    fi
    exit 0
fi

if [[ -n "${1:-}" ]]; then
    echo "usage: probe-memory-headroom.sh [--human]" >&2
    exit 2
fi

echo "ram_available_mb=${RAM_AVAIL_MB}"
echo "ram_total_mb=${RAM_TOTAL_MB}"
echo "vram_free_mb=${VRAM_FREE_MB}"
echo "vram_total_mb=${VRAM_TOTAL_MB}"
