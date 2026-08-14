# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-engine-drift.py -- CLI trampoline: read-only consumer of claude-klabauter's
registered "engine.drift" op, via coordinator/bin/lib/cc_invoke.py.

Purpose: surface claude-klabauter's registered engine.drift freshness probe during
fleet /workday-start, mirroring how check-claude-klabauter-doctor-sentinel.sh nudges
on the doctor sentinel. This is a READ-CONSUMER only -- the op is owned and
invoked by claude-klabauter's coordinator_core package; this script never writes
anything, it only invokes and renders.

Filename note: renamed from `check-engine-drift.sh` to `check-engine-drift.py`
under the Wave 4a de-bash campaign (the sh/python polyglot trampoline this
file previously carried added ~326ms/invocation on Windows for zero bash
content). Callers were repointed in the same wave; invoke directly or via
`python check-engine-drift.py`.

No new claude-klabauter module authored for this port: the engine-side probe logic
already lives entirely in claude-klabauter's registered "engine.drift" op
(coordinator_core/ops/engine_drift.py, @register_op, async handler) -- this
script is, and was already (per its own prior header), a pure CLI-rendering
veneer with no legacy body to strangle (same shape as
handoff-has-live-children.sh, R1 DOE-PORT template Section 4). The port
converts the bash veneer's manual two-stage interpreter resolution plus a
raw subprocess spawn plus an inline "python3 -c" JSON parse into a direct
call to the EXISTING DoE-side Python transport,
coordinator/bin/lib/cc_invoke.py's cc_invoke() function (itself a straight
port of coordinator/lib/coordinator-core-invoke.sh's cc_invoke, DR-215) --
reusing it rather than re-deriving a second transport.

Interpreter-fidelity note (expected, not a regression): the original .sh did
a full coordinator_core.pyresolve --print-bin resolve (COORDINATOR_PYTHON
pin -> machine-local pin -> OS-detect) for the invoke call specifically.
cc_invoke.py's cc_invoke() spawns coordinator_core.invoke via sys.executable
(the interpreter already running this trampoline, itself resolved by the
polyglot shebang's `python3 || python || py` probe) -- this is the SAME
convention every other migrated trampoline in this repo uses (coordinator-
auto-push, handoff-gate-aging, et al.); narrowing to sys.executable here
brings this script into line with that fleet-wide convention rather than
carrying a one-off bespoke resolution path forward.

Invoke contract (via cc_invoke.cc_invoke("engine.drift", {}, repo_root)):
  Returns the bare `result` dict on success:
    {"state":"clean|behind|indeterminate", "running_sha":..., "floor_sha":...,
     "offer":"<str, state=behind only>", "notice":"<str, state=indeterminate only>"}
  Raises RuntimeError on ANY transport failure (unresolved CLAUDE_KLABAUTER_ROOT,
  timeout, ImportError, op-error envelope, malformed stdout) -- treated as a
  silent skip here, matching the original's fail-silent/never-nag posture.

Three-state rendering + error-silent rule (unchanged from the original):
  - transport failure / RuntimeError (op unregistered / claude-klabauter not ready) -> silent.
  - result["state"] == "clean" -> silent (engine fresh, nothing to say).
  - result["state"] == "behind" -> print result["offer"].
  - result["state"] == "indeterminate" -> print result["notice"].
  - any other/unknown/missing state -> silent.

Output: zero or one line of the form
  [health] engine-drift: <message>
Exit 0 always (advisory, never gating) -- matches check-claude-klabauter-doctor-sentinel.sh
/ check-plugin-drift.py convention of "probe never fails the ceremony".

Test seam (test-only): when COORDINATOR_ENGINE_DRIFT_JSON is set and
non-empty, its value is parsed AS the bare `result` dict payload directly
(mirrors the pre-port seam's JSON-RPC-envelope contract: a `result` key is
unwrapped, an `error` key renders silent, and malformed JSON renders silent)
-- the real cc_invoke() call below is skipped entirely. This lets
check-engine-drift.test.sh drive the rendering logic without a live claude-klabauter
checkout. The seam is checked BEFORE CLAUDE_KLABAUTER_ROOT resolution so tests do not
need a real claude-klabauter checkout to exercise it.

Spec backlink: cross-repo/inbox/2026-07-12-claude-klabauter-em-engine-drift-workday-start-cadence.md
Port backlink: tasks/2026-07-16-clean-slate-recon/r1-doe-port-template.md

Negative-spec:
  - Does NOT write anything -- claude-klabauter's engine.drift op owns its own state.
  - Does NOT hardcode CLAUDE_KLABAUTER_ROOT -- resolves via cc_invoke's
    _resolve_claude_klabauter_root() (env var -> settings-home pointer -> bash resolver).
  - Does NOT hard-error or nag when the op is unregistered/claude-klabauter absent --
    degrades to a fully silent skip (exit 0, no output). DoE is a consumer;
    it must never nag about claude-klabauter's activation state.
  - Does NOT re-implement the invoke transport -- imports and calls cc_invoke().
"""

from __future__ import annotations

import json
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


def _fetch_result() -> dict:
    """Return the bare engine.drift result dict, or {} on any failure/skip.

    Test seam: COORDINATOR_ENGINE_DRIFT_JSON, when set and non-empty, supplies
    the bare result payload directly (same shape cc_invoke() would return on
    success) -- an "error" key or malformed JSON both degrade to {} (silent).
    """
    seam = os.environ.get("COORDINATOR_ENGINE_DRIFT_JSON", "")
    if seam:
        try:
            envelope = json.loads(seam)
        except (json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(envelope, dict):
            return {}
        if "error" in envelope:
            return {}
        result = envelope.get("result", {})
        return result if isinstance(result, dict) else {}

    from cc_invoke import _resolve_claude_klabauter_root, cc_invoke  # noqa: E402

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError:
        return {}
    if not claude_klabauter_root:
        return {}

    try:
        result = cc_invoke("engine.drift", {}, claude_klabauter_root)
    except RuntimeError:
        return {}
    return result if isinstance(result, dict) else {}


def main() -> int:
    result = _fetch_result()
    state = result.get("state", "")

    if state == "behind":
        message = result.get("offer", "")
    elif state == "indeterminate":
        message = result.get("notice", "")
    else:
        return 0

    if message:
        print(f"[health] engine-drift: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
