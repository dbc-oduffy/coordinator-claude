#!/usr/bin/env bash
# emit-cockpit-snapshot.sh — DR-210 facade router: artifact.emit (strang-01 C2).
#
# Purpose: routes artifact.emit through the example-orchestration-hub UDS client (native-primary).
# The original bash script body is no longer retained — it was ported to
# example-orchestration-hub's Python `artifact.emit` (DR-208 tri-plane relocation) — so the
# disk-absence fallback now fails loud instead of re-running a bash emitter.
# Three-state routing model (Design pin 3):
#   State 1 (seam absent on disk) -> legacy_emit fails loud (no bash emitter
#     body retained; ported to example-orchestration-hub artifact.emit). No snapshot is written.
#   State 2 (seam present + daemon idle-shut) -> C1 client lazy-launches, then RPC.
#   State 3 (seam present + post-spawn unreachable) -> hard transport error, fail loud.
#
# Spec backlink: docs/plans/2026-07-08-retire-js-cockpit-emitter-lockstep.md § D1 (Option 2)
# Prior backlink: docs/plans/2026-07-04-strang-01-tc3-emission-port-facade-respin.md § C2
# Prior backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C5
#
# Usage (unchanged from pre-facade — zero caller repoints, AC8):
#   emit-cockpit-snapshot.sh
#   emit-cockpit-snapshot.sh --out /path/to/output.json
#
# Exit codes:
#   0 — success, cockpit-emission.json written (native path only)
#   1 — State-1 fail-loud (seam absent, no bash emitter body retained)
#   3 — native op: post-spawn transport failure (State 3, native path only)
set -euo pipefail

# ---------------------------------------------------------------------------
# DR-210 facade router — source shared helper (C4b, must precede legacy_emit).
# ---------------------------------------------------------------------------
_FACADE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/strangler-facade.sh
source "${_FACADE_SCRIPT_DIR}/../lib/strangler-facade.sh"

# ---------------------------------------------------------------------------
# legacy_emit — State-1 fallback. Fails loud rather than re-running a bash
# emitter body (see header comment above for the DR-208 relocation rationale).
# Called ONLY on State 1 (coordinator_core.client absent on disk).
# ---------------------------------------------------------------------------
legacy_emit() {
  # State-1 fallback: the example-orchestration-hub control-plane seam is absent on disk.
  # The cockpit emitter was ported to example-orchestration-hub's Python `artifact.emit` (DR-208 tri-plane
  # relocation); DoE no longer carries a bash emitter body. Fail loud rather than write an
  # empty-DAG snapshot over example-orchestration-hub's authoritative state.
  # Spec: docs/plans/2026-07-08-retire-js-cockpit-emitter-lockstep.md § D1 (Option 2)
  echo "emit-cockpit-snapshot: cockpit emission requires the example-orchestration-hub control plane, which is not present in this distribution. No snapshot written." >&2
  return 1
}

# ---------------------------------------------------------------------------
# Build artifact.emit params JSON from CLI args.
# --out <path> maps to params.out (artifact_emit.py § Params).
# Safe JSON construction via jq avoids path-character injection.
# ---------------------------------------------------------------------------
_EMIT_PARAMS='{}'
if [[ "${1:-}" == "--out" && -n "${2:-}" ]]; then
  _EMIT_PARAMS="$(jq -cn --arg out "${2}" '{out: $out}')"
fi

# ---------------------------------------------------------------------------
# Three-state facade dispatch.
# strangle_route decides: seam-absent -> legacy_emit "$@";
#                         seam-present -> python3 -m coordinator_core.client artifact.emit.
# "$@" forwarded verbatim so legacy_emit receives original CLI args unchanged.
# ---------------------------------------------------------------------------
strangle_route "artifact.emit" "legacy_emit" "$_EMIT_PARAMS" "$@"
