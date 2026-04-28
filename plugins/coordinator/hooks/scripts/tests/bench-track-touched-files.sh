#!/bin/bash
# Benchmark: track-touched-files.sh — latency over 100 fires
#
# Measures wall-clock time per hook invocation using a synthesized JSON input.
# Prints p50/p95/p99 in milliseconds.
# Target: p95 < 50ms on Windows + Git Bash.
#
# Usage: bash bench-track-touched-files.sh [N]
#   N: number of iterations (default 100)

set -euo pipefail

HOOK_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../track-touched-files.sh"
N="${1:-100}"

if [[ ! -f "$HOOK_SCRIPT" ]]; then
  echo "FATAL: hook not found: $HOOK_SCRIPT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Setup: temporary git repo
# ---------------------------------------------------------------------------
TMPDIR_BASE=$(mktemp -d 2>/dev/null || mktemp -d -t bench-track)
trap 'rm -rf "$TMPDIR_BASE"' EXIT

REPO="$TMPDIR_BASE/repo"
mkdir -p "$REPO"
cd "$REPO"
git init -q
git config user.email "bench@bench.com"
git config user.name "Bench"
touch README.md && git add README.md && git commit -q -m "init"

SID="bench-session-001"
INPUT='{"session_id":"'"$SID"'","tool_name":"Write","tool_input":{"file_path":"src/target.ts"}}'

echo "Warming up (5 runs)..."
for i in $(seq 1 5); do
  echo "$INPUT" | bash "$HOOK_SCRIPT" > /dev/null 2>&1 || true
done

echo "Benchmarking $N iterations..."

TIMES=()
for i in $(seq 1 "$N"); do
  # Rotate file path to exercise dedup path and non-dedup path alternately
  if (( i % 2 == 0 )); then
    TEST_INPUT='{"session_id":"'"$SID"'","tool_name":"Write","tool_input":{"file_path":"src/file-'"$i"'.ts"}}'
  else
    TEST_INPUT="$INPUT"
  fi

  START=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo 0)
  echo "$TEST_INPUT" | bash "$HOOK_SCRIPT" > /dev/null 2>&1 || true
  END=$(date +%s%3N 2>/dev/null || python3 -c "import time; print(int(time.time()*1000))" 2>/dev/null || echo 0)

  ELAPSED=$(( END - START ))
  TIMES+=("$ELAPSED")
done

# ---------------------------------------------------------------------------
# Compute percentiles (pure bash sort + index)
# ---------------------------------------------------------------------------
IFS=$'\n' SORTED=($(printf '%s\n' "${TIMES[@]}" | sort -n))
unset IFS

COUNT=${#SORTED[@]}

# p50: index at 50% (0-indexed: floor((N-1)*0.50))
P50_IDX=$(( (COUNT - 1) * 50 / 100 ))
# p95: index at 95%
P95_IDX=$(( (COUNT - 1) * 95 / 100 ))
# p99: index at 99%
P99_IDX=$(( (COUNT - 1) * 99 / 100 ))

P50="${SORTED[$P50_IDX]}"
P95="${SORTED[$P95_IDX]}"
P99="${SORTED[$P99_IDX]}"

MIN="${SORTED[0]}"
MAX="${SORTED[$((COUNT-1))]}"

SUM=0
for t in "${TIMES[@]}"; do SUM=$(( SUM + t )); done
AVG=$(( SUM / COUNT ))

echo ""
echo "=== track-touched-files.sh benchmark ==="
echo "  Iterations : $N"
echo "  Min        : ${MIN}ms"
echo "  Avg        : ${AVG}ms"
echo "  p50        : ${P50}ms"
echo "  p95        : ${P95}ms"
echo "  p99        : ${P99}ms"
echo "  Max        : ${MAX}ms"
echo ""

if [[ "$P95" -lt 50 ]]; then
  echo "PASS: p95 ${P95}ms < 50ms target"
  exit 0
else
  echo "WARN: p95 ${P95}ms >= 50ms target — consider optimizing hot path"
  # Not a hard failure — report and allow the caller to decide.
  # The plan says "optimize before declaring DONE if it fails", so we exit 1
  # to make the failure visible in CI/test runs.
  exit 1
fi
