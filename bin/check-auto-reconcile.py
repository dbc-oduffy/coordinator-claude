# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
bin/check-auto-reconcile.sh -- CLI trampoline over the engine repo's
coordinator_core.ops.check_auto_reconcile, rendering the "handoff.reconcile_open"
op's surfaced[] list for the DoE fleet /workday-start Morning Briefing.

Purpose: surface the engine repo's registered handoff.reconcile_open op during fleet
/workday-start, mirroring how check-engine-drift.py nudges on the
engine.drift probe. This is a READ-CONSUMER only -- this script itself never
writes anything and never passes a dry_run flag of its own, forced or
otherwise; it always invokes with the op's own default resolution.

POST-D2(a) UPDATE (2026-07-27, docs/plans/2026-07-26-push-side-write-
discipline.md § D2): the op's dry_run resolution changed underneath this
script -- the loaded DoE `auto-reconcile-policy.yaml`'s own `dry_run` key is
now the SOLE source of truth (coordinator_core/reconcile/policy_loader.py +
coordinator_core/ops/handoff_reconcile.py::_resolve_dry_run), not a
caller-params-only default. This script SHOULD KEEP not passing a `dry_run`
param -- not-passing correctly means "defer to policy" now, same as it always
claimed to mean. But the OLD claim that the invoked op therefore "never
writes anything" is NO LONGER TRUE for every repo: whenever the policy it
loads declares `dry_run: false` (an explicit, present, valid, DoE-authored
posture -- see policy_loader.py's fail-closed default, which still yields
`dry_run: true` on any absent/malformed policy), this script's ordinary,
unmodified invocation now drives a WRITE-CAPABLE path
(handoff.ship_and_archive / handoff.transition gate-cascade-clear) rather than
a pure read. This script's OWN behavior (no flag passed, no write performed
BY this script) is unchanged; what changed is what "the op's own default"
resolves to. A stale negative-spec asserting "does not write anything" on a
now-write-capable path is exactly the kind of claim that gets trusted later
without re-checking -- see the corrected Negative-spec below.

Invoke contract: the engine repo's coordinator_core.ops.check_auto_reconcile.get_response()
runs the already-registered "handoff.reconcile_open" op in-process (no
subprocess hop) and returns the bare JSON-RPC 2.0 response dict:
  Success: {"jsonrpc":"2.0","id":1,"result":{"reconciled":[...],
            "gates_cleared":[...],
            "surfaced":[{"handoff_id":"...","reason":"...","evidence":"..."}],
            "exit_code":0}}
  Error:   {"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"..."}}

NO dry_run flag is ever passed on this invocation -- the op defaults
dry_run=true, and this consumer script deliberately never overrides that
default (observation-only cadence; forcing a live reconcile from a daily
health probe is out of scope and not this repo's call to make).

Dual silent-skip rule (mirrors check-engine-drift.py's error-silent rule,
doubled for this op's provisional-registration window):
  (a) CLAUDE_KLABAUTER_ROOT cannot resolve (no engine checkout on this machine) --
      a fleet-topology fact, not a health regression.
  (b) .error present in the envelope, or the engine-side module/op is not
      importable (provisional-op rollout window) -- DoE is a consumer and
      must never nag about the engine repo's activation state.
Both cases: exit 0, no output, no error.

Render rule (offers-not-nags): result.surfaced empty or missing -> silent
(nothing to report). result.surfaced non-empty -> one line per entry:
  [auto-reconcile] <handoff_id>: <reason> — <evidence>
(the " — <evidence>" tail is omitted when evidence is empty/missing).
result.gates_cleared[] additionally renders one would-flip line per entry
where dry_run is truthy AND blocker_ids is non-empty (a dry-run clear/narrow
verdict never reaches surfaced[] -- see handoff_reconcile.py's routing
docstring -- so this is the only operator-visible signal it produces):
  [auto-reconcile] <handoff_id>: gate cleared — would flip awaiting_gate →
  <target> (dry-run, not applied) — blockers: <ids>
An entry with empty blocker_ids (the non-dry-run vacuous no-op shape) is
never rendered -- nothing to announce.
Malformed/unparseable JSON -> silent, never crash. Exit 0 always.

Rendering is deliberately self-contained (no engine import) so the
COORDINATOR_AUTO_RECONCILE_JSON test seam below can exercise it without any
engine checkout registered anywhere -- envelope-parsing/rendering is a DoE-side
concern; the engine repo's module owns only the dispatch step.

Test seam (test-only): when COORDINATOR_AUTO_RECONCILE_JSON is set and
non-empty, its value is used AS the invoke output -- the actual engine-repo call
below is skipped entirely -- and parsed normally. This lets
check-auto-reconcile.test.sh drive the rendering logic without a live op
or a real engine checkout. The seam is checked BEFORE the CLAUDE_KLABAUTER_ROOT gate
below, same ordering rationale as check-engine-drift.py.

Spec backlink: DoE-claude:pln-doe-side-adoption-of-claude-klabauter-au-284ced (C1) +
cross-repo/inbox/2026-07-13-claude-klabauter-em-claude-klabauter-auto-reconcile-wire-surfaces.md

Engine-side dispatch: coordinator_core/ops/check_auto_reconcile.py::get_response().

Negative-spec:
  - THIS SCRIPT does NOT write anything itself, and does NOT pass a dry_run
    flag, forced or otherwise -- always invokes with the op's own default
    resolution. But post-D2(a), the OP it invokes owns a dry_run default that
    is no longer hard-coded true -- it resolves from the loaded DoE policy,
    so the INVOKED OP may perform real writes (ship_and_archive /
    gate-cascade-clear) on this script's ordinary, unmodified invocation
    whenever that policy declares `dry_run: false`. "This script never
    writes anything" is true of this script's own code; it is NOT a
    guarantee that invoking it is side-effect-free end to end. Any dry_run
    flag it does not pass belongs to policy_loader.py's own fail-closed
    default (true on any absent/malformed policy), not to this script.
  - Does NOT hardcode CLAUDE_KLABAUTER_ROOT -- resolves via cc_invoke.ensure_engine_on_path()
    (bin/lib/cc_invoke.py): CLAUDE_KLABAUTER_ROOT env -> self-location walk-up to the
    enclosing engine checkout -> the pointer-file/registry ladder.
  - Does NOT hard-error or nag when the op is unregistered/engine absent --
    degrades to a fully silent skip (exit 0, no output). DoE is a consumer;
    it must never nag about the engine repo's activation state.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import ensure_engine_on_path  # noqa: E402


def _render(response: Any) -> List[str]:
    """Render result.surfaced[] as one '[auto-reconcile] ...' line per entry,
    PLUS one dry-run would-flip line per qualifying result.gates_cleared[]
    entry (clear/narrow verdicts computed under dry_run=true never reach
    surfaced[] -- see handoff_reconcile.py's D1/gate_evidence docstring
    sections -- so this second pass is the only operator-visible signal a
    dry-run gate-clear produces at all).

    Self-contained (no engine import) -- see module docstring.
    """
    if not isinstance(response, dict):
        return []
    if "error" in response:
        return []
    result = response.get("result") or {}
    if not isinstance(result, dict):
        return []
    surfaced = result.get("surfaced") or []
    if not isinstance(surfaced, list):
        surfaced = []
    lines: List[str] = []
    for entry in surfaced:
        if not isinstance(entry, dict):
            continue
        handoff_id = str(entry.get("handoff_id", "")).replace("\n", " ").replace("\r", " ")
        reason = str(entry.get("reason", "")).replace("\n", " ").replace("\r", " ")
        evidence = str(entry.get("evidence", "")).replace("\n", " ").replace("\r", " ")
        line = "[auto-reconcile] {}: {}".format(handoff_id, reason)
        if evidence:
            line += " — {}".format(evidence)
        lines.append(line)

    gates_cleared = result.get("gates_cleared") or []
    if not isinstance(gates_cleared, list):
        gates_cleared = []
    for entry in gates_cleared:
        if not isinstance(entry, dict):
            continue
        blocker_ids = entry.get("blocker_ids") or []
        if not entry.get("dry_run") or not isinstance(blocker_ids, list) or not blocker_ids:
            continue
        handoff_id = str(entry.get("handoff_id", "")).replace("\n", " ").replace("\r", " ")
        verdict = str(entry.get("verdict", "")).replace("\n", " ").replace("\r", " ")
        blockers = ", ".join(str(b).replace("\n", " ").replace("\r", " ") for b in blocker_ids)
        target = "ready_to_fire" if verdict == "clear" else "awaiting_gate (narrowed)"
        lines.append(
            "[auto-reconcile] {}: gate cleared — would flip awaiting_gate → {} "
            "(dry-run, not applied) — blockers: {}".format(handoff_id, target, blockers)
        )
    return lines


def _get_raw_response() -> Optional[Dict[str, Any]]:
    """Return the parsed JSON-RPC response dict, or None on any silent-skip
    condition (test-seam malformed JSON, CLAUDE_KLABAUTER_ROOT unresolved, engine
    module/op not importable, dispatch failure)."""
    raw_env = os.environ.get("COORDINATOR_AUTO_RECONCILE_JSON", "")
    if raw_env:
        try:
            return json.loads(raw_env)
        except Exception:
            return None

    claude_klabauter_root = ensure_engine_on_path(__file__)
    if not claude_klabauter_root:
        return None

    try:
        from coordinator_core.ops.check_auto_reconcile import get_response
    except ImportError:
        return None

    try:
        return get_response()
    except Exception:
        return None


def main() -> None:
    response = _get_raw_response()
    if response is None:
        sys.exit(0)
    try:
        lines = _render(response)
    except Exception:
        sys.exit(0)
    for line in lines:
        print(line)
    sys.exit(0)


if __name__ == "__main__":
    main()
