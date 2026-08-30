# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-deferral-orphan-memo.py -- CLI trampoline: read-only consumer of
Claude-klabauter's registered "deferral.detect_orphan_memo" op, via
coordinator/bin/lib/cc_invoke.py.

Purpose: surface claude-klabauter's registered orphaned-aging-deferral-memo detector
during fleet /workday-start -- Detector 2 of the hidden-deferral-detectors
pair (Detector 1 is deferral.detect_partial_strangle, surfaced by the
sibling check-deferral-partial-strangle veneer). This is a READ-CONSUMER
only -- the op is owned and invoked by claude-klabauter's coordinator_core package;
this script never writes anything, it only invokes and renders. Same
template as check-engine-drift.py (R1 DOE-PORT template Section 4): a pure
CLI-rendering veneer with no legacy body to strangle, reusing the EXISTING
DoE-side Python transport, coordinator/bin/lib/cc_invoke.py's cc_invoke().

Invoke contract (via cc_invoke.cc_invoke("deferral.detect_orphan_memo", {},
repo_root)): Returns the bare `result` dict on success:
  {"state": "clean"} -- no orphaned-aging memo found.
  {"state": "orphans_found", "findings": [...], "offer": "<str>"} -- one or
    more inbox memos are actionable, aging, and unowned.
Raises RuntimeError on ANY transport failure (an unresolved engine root,
timeout, ImportError, op-error envelope, malformed stdout) -- treated as a
silent skip here, matching check-engine-drift.py's fail-silent/never-nag
posture.

Two-state rendering + error-silent rule (this detector, unlike engine.drift,
has no indeterminate leg -- its inputs are never unverifiable the way engine
SHA ancestry can be):
  - transport failure / RuntimeError (op unregistered / claude-klabauter not ready) -> silent.
  - result["state"] == "orphans_found" -> print result["offer"].
  - result["state"] == "clean" -> silent (nothing orphaned, nothing to say).
  - any other/unknown/missing state -> silent.

Output: zero or one line of the form
  [health] deferral-orphan-memo: <message>
Exit 0 always (advisory, never gating) -- matches check-engine-drift.py /
Check-claude-klabauter-doctor-sentinel.sh convention of "probe never fails the
ceremony".

Test seam (test-only): when COORDINATOR_DEFERRAL_ORPHAN_MEMO_JSON is set and
non-empty, its value is parsed AS the bare `result` dict payload directly
(mirrors check-engine-drift.py's pre-port seam: a `result` key is unwrapped,
an `error` key renders silent, and malformed JSON renders silent) -- the
real cc_invoke() call below is skipped entirely. This lets
check-deferral-orphan-memo.test.sh drive the rendering logic without a live
Claude-klabauter checkout. The seam is checked BEFORE engine-root resolution so tests
do not need a real claude-klabauter checkout to exercise it.

Spec backlink: cross-repo/inbox/2026-07-21-claude-klabauter-em-deferral-detectors-workday-start.md

Negative-spec:
  - Does NOT write anything -- claude-klabauter's deferral.detect_orphan_memo op owns
    its own state (this repo's cross-repo/inbox/ is read, never mutated).
  - Does NOT hardcode the engine root -- resolves via cc_invoke's
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



def _fetch_result() -> dict:
    """Return the bare deferral.detect_orphan_memo result dict, or {} on any
    failure/skip.

    Test seam: COORDINATOR_DEFERRAL_ORPHAN_MEMO_JSON, when set and non-empty,
    supplies the bare result payload directly (same shape cc_invoke() would
    return on success) -- an "error" key or malformed JSON both degrade to
    {} (silent).
    """
    seam = os.environ.get("COORDINATOR_DEFERRAL_ORPHAN_MEMO_JSON", "")
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

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import _resolve_claude_klabauter_root, cc_invoke  # noqa: E402

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError:
        return {}
    if not claude_klabauter_root:
        return {}

    try:
        result = cc_invoke("deferral.detect_orphan_memo", {}, claude_klabauter_root)
    except RuntimeError:
        return {}
    return result if isinstance(result, dict) else {}


def main(argv: "list[str] | None" = None) -> int:
    del argv  # this CLI takes no arguments; argv accepted for the warm-call contract
    result = _fetch_result()
    state = result.get("state", "")

    if state != "orphans_found":
        return 0

    message = result.get("offer", "")
    if message:
        print(f"[health] deferral-orphan-memo: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
