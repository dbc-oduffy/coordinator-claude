#!/usr/bin/env bash
# bin/console-flash-repro.sh — deterministic console-window-flash reproducer
#
# PURPOSE: Measurement instrument for the Windows Terminal / ConPTY machine-belt
# experiment. Spawns native console exes in a tight loop from git-bash/mintty so
# a human observer can COUNT how many visible window flashes occur per exe type.
#
# THIS SCRIPT IS READ-ONLY WITH RESPECT TO YOUR MACHINE.
# It does NOT modify the registry. It does NOT change your terminal default.
# It does NOT change Windows Settings. It spawns processes and prints counts.
# The only side-effect is transient child processes that exit immediately.
#
# Spec backlink: docs/plans/2026-05-29-windows-console-flash-elimination.md § Chunk 5
#
# USAGE:
#   bash bin/console-flash-repro.sh [N]
#
#   N  Number of times to spawn each exe (default: 10).
#      A tight loop of 10 is enough for a human to count; use 20 for a clearer
#      cascade if flashes are intermittent.
#
# INTERPRETATION:
#   - Each spawn creates a native console-subsystem child from mintty's non-console
#     parent. Windows must allocate a fresh conhost.exe window for each child,
#     which flashes briefly and disappears when the child exits.
#   - Record the flash count per exe type in the results table in:
#       docs/wiki/windows-console-flash-belt-experiment.md
#   - Then apply the machine-belt lever (Windows Terminal default-terminal / delegation
#     setting) per that document's instructions and re-run this script to fill the
#     After column.
#
# IMPORTANT: Run this script from git-bash or mintty — NOT from Windows Terminal
# directly. The flash only occurs when the spawning parent is a non-console host
# (mintty). Running from WT's own ConPTY would pre-apply the belt and give you
# a false "no flashes" baseline.

set -euo pipefail

N="${1:-10}"

# Validate N is a positive integer.
if ! [[ "$N" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: N must be a positive integer, got: $N" >&2
  exit 1
fi

echo "============================================================"
echo "  console-flash-repro.sh — Windows console-window flash test"
echo "============================================================"
echo ""
echo "  IMPORTANT: Run this script from git-bash / mintty."
echo "  Do NOT run from Windows Terminal — that would pre-apply"
echo "  the machine-belt and invalidate the baseline measurement."
echo ""
echo "  THIS SCRIPT DOES NOT MODIFY YOUR MACHINE."
echo "  No registry writes. No settings changes. Read-only."
echo ""
echo "  Watch the screen carefully and COUNT the visible flashes"
echo "  for each phase below. Record your counts in:"
echo "    docs/wiki/windows-console-flash-belt-experiment.md"
echo ""
echo "  N = $N spawns per exe type."
echo "  Press ENTER to begin..."
read -r

# --------------------------------------------------------------------------
# Phase 1 — python
# --------------------------------------------------------------------------
echo ""
echo "--- PHASE 1: python  ($N spawns) ---"
echo "Watch the screen. Counting visible flashes now..."
echo ""

python_found=false
for candidate in python python3 python.exe; do
  if command -v "$candidate" &>/dev/null; then
    python_cmd="$candidate"
    python_found=true
    break
  fi
done

# Review: code-reviewer (F12) — replace `if $var` boolean-command idiom with explicit
#   string comparison to avoid accidental command execution if var is non-empty/non-bool.
if [[ "$python_found" == true ]]; then
  for (( i=1; i<=N; i++ )); do
    "$python_cmd" -c "pass"
  done
  echo "python: $N spawns complete."
else
  echo "python: NOT FOUND on PATH — skipped. Install Python and re-run."
fi

echo ""
echo ">>> Write down how many python flashes you saw, then press ENTER to continue..."
read -r

# --------------------------------------------------------------------------
# Phase 2 — node
# --------------------------------------------------------------------------
echo ""
echo "--- PHASE 2: node  ($N spawns) ---"
echo "Watch the screen. Counting visible flashes now..."
echo ""

node_found=false
for candidate in node node.exe; do
  if command -v "$candidate" &>/dev/null; then
    node_cmd="$candidate"
    node_found=true
    break
  fi
done

if [[ "$node_found" == true ]]; then
  for (( i=1; i<=N; i++ )); do
    "$node_cmd" -e "0"
  done
  echo "node: $N spawns complete."
else
  echo "node: NOT FOUND on PATH — skipped. Install Node.js and re-run."
fi

echo ""
echo ">>> Write down how many node flashes you saw, then press ENTER to continue..."
read -r

# --------------------------------------------------------------------------
# Phase 3 — powershell.exe  (legacy Windows PowerShell, the blue window)
# --------------------------------------------------------------------------
echo ""
echo "--- PHASE 3: powershell.exe  ($N spawns) ---"
echo "This spawns the LEGACY blue Windows PowerShell window."
echo "Watch the screen. Counting visible flashes now..."
echo ""

ps_found=false
for candidate in powershell.exe powershell; do
  if command -v "$candidate" &>/dev/null; then
    ps_cmd="$candidate"
    ps_found=true
    break
  fi
done

if [[ "$ps_found" == true ]]; then
  for (( i=1; i<=N; i++ )); do
    "$ps_cmd" -NoProfile -NonInteractive -Command "exit 0"
  done
  echo "powershell.exe: $N spawns complete."
else
  echo "powershell.exe: NOT FOUND on PATH — skipped."
fi

echo ""
echo ">>> Write down how many powershell flashes you saw, then press ENTER to continue..."
read -r

# --------------------------------------------------------------------------
# Phase 4 — pwsh  (PowerShell 7 / pwsh.exe)
# --------------------------------------------------------------------------
echo ""
echo "--- PHASE 4: pwsh  ($N spawns) ---"
echo "This spawns PowerShell 7 (pwsh). Watch for a smaller dark window."
echo "Watch the screen. Counting visible flashes now..."
echo ""

pwsh_found=false
for candidate in pwsh pwsh.exe; do
  if command -v "$candidate" &>/dev/null; then
    pwsh_cmd="$candidate"
    pwsh_found=true
    break
  fi
done

if [[ "$pwsh_found" == true ]]; then
  for (( i=1; i<=N; i++ )); do
    "$pwsh_cmd" -NoProfile -NonInteractive -Command "exit 0"
  done
  echo "pwsh: $N spawns complete."
else
  echo "pwsh: NOT FOUND on PATH — skipped. Install PowerShell 7 and re-run."
fi

echo ""
echo ">>> Write down how many pwsh flashes you saw."
echo ""

# --------------------------------------------------------------------------
# Summary prompt
# --------------------------------------------------------------------------
echo "============================================================"
echo "  All phases complete."
echo ""
echo "  Record your flash counts in the Before column of the table at:"
echo "    docs/wiki/windows-console-flash-belt-experiment.md"
echo ""
echo "  Then follow that document's instructions to apply the"
echo "  machine-belt lever (Windows Terminal default-terminal /"
echo "  delegation setting) and re-run this script to fill the After column."
echo "============================================================"
