#!/usr/bin/env bash
# emit-cockpit-spine-graceful-absent.sh — State-1 fail-loud contract test
#
# Asserts that when the example-orchestration-hub control-plane seam is absent on disk (State 1
# of the DR-210 three-state facade), emit-cockpit-snapshot.sh fails loud
# (non-zero exit, no snapshot file written, diagnostic message on stderr)
# rather than falling back to a bash emitter body. The bash emitter was
# ported to example-orchestration-hub's Python `artifact.emit` (DR-208 tri-plane relocation);
# DoE no longer carries a bash emitter body to fall back to.
#
# This test REPLACES the prior AC4 graceful-absent-spine-arrays test, which
# asserted the inverse contract (native-path success + empty spine arrays).
# That assertion shape is stale post-DR-208: State 1 now must fail loud, not
# silently emit an empty-DAG snapshot over example-orchestration-hub's authoritative state.
#
# Spec backlink: docs/plans/2026-07-08-retire-js-cockpit-emitter-lockstep.md § D1 (Option 2)
# Prior backlink: docs/plans/2026-06-30-ccos-8-cockpit-read-contract-spine-entities.md § AC4
#
# Usage: bash bin/emit-cockpit-spine-graceful-absent.sh
# Exit 0 = GREEN; exit 1 = RED with diagnostic on stderr.
set -euo pipefail

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "ERROR: bash >= 4 required. On macOS: brew install bash" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

EMIT_SCRIPT="$SCRIPT_DIR/emit-cockpit-snapshot.sh"
if [[ ! -f "$EMIT_SCRIPT" ]]; then
  echo "RED: emitter not found at $EMIT_SCRIPT" >&2
  exit 1
fi

fail() { echo "RED: $1" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Force State 1 (seam absent) via the documented test lever, per
# coordinator/lib/strangler-facade.sh — COORDINATOR_FORCE_LEGACY=1.
# ---------------------------------------------------------------------------
TMP_OUT="$(mktemp "${TMPDIR:-/tmp}/cockpit-absent-out.XXXXXX")"
rm -f "$TMP_OUT"
trap 'rm -f "$TMP_OUT"' EXIT

echo "[State-1] running emitter --out $TMP_OUT with COORDINATOR_FORCE_LEGACY=1 ..." >&2
_EMIT_STDERR="$(mktemp "${TMPDIR:-/tmp}/cockpit-absent-stderr.XXXXXX")"
trap 'rm -f "$TMP_OUT" "$_EMIT_STDERR"' EXIT

_EMIT_EXIT=0
COORDINATOR_FORCE_LEGACY=1 bash "$EMIT_SCRIPT" --out "$TMP_OUT" >/dev/null 2>"$_EMIT_STDERR" || _EMIT_EXIT=$?

# ---------------------------------------------------------------------------
# Assert fail-loud contract: non-zero exit, no snapshot written, diagnostic
# message present on stderr.
# ---------------------------------------------------------------------------
if [[ "$_EMIT_EXIT" -eq 0 ]]; then
  fail "emitter exited 0 under State 1 (seam absent) — expected fail-loud non-zero exit"
fi

if [[ -e "$TMP_OUT" ]]; then
  fail "emitter wrote a snapshot file at $TMP_OUT under State 1 — expected no file written"
fi

if ! grep -q "requires the example-orchestration-hub control plane" "$_EMIT_STDERR"; then
  fail "fail-loud message not found on stderr (expected substring: 'requires the example-orchestration-hub control plane')"
fi

echo "GREEN: State 1 — seam absent → emitter fails loud (exit $_EMIT_EXIT), no snapshot written, diagnostic on stderr" >&2
