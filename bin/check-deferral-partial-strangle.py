# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-deferral-partial-strangle.py -- CLI trampoline: read-only consumer of
Claude-klabauter's registered "deferral.detect_partial_strangle" op, via
coordinator/bin/lib/cc_invoke.py.

Purpose: surface claude-klabauter's registered partial-strangle deferral probe during
fleet /workday-start, mirroring how check-engine-drift.py nudges on engine
freshness drift. This is a READ-CONSUMER only -- the op is owned and invoked
by claude-klabauter's coordinator_core package; this script never writes anything, it
only invokes and renders.

Invoke contract (via
cc_invoke.cc_invoke("deferral.detect_partial_strangle", {}, repo_root)):
  Returns the bare `result` dict on success:
    {"state":"partial_strangles_found|indeterminate|clean", ...,
     "offer":"<str, state=partial_strangles_found only>",
     "notice":"<str, state=indeterminate only>"}
  Raises RuntimeError on ANY transport failure (an unresolved engine root,
  timeout, ImportError, op-error envelope, malformed stdout) -- treated as a
  silent skip here, matching check-engine-drift.py's fail-silent/never-nag
  posture.

Three-state rendering + error-silent rule:
  - transport failure / RuntimeError (op unregistered / claude-klabauter not ready) -> silent.
  - result["state"] == "partial_strangles_found" -> print result["offer"].
  - result["state"] == "indeterminate" -> print result["notice"].
  - any other/unknown/missing state (including "clean") -> silent.

Deliberate choice (not an oversight): a "partial_strangles_found" result may
also carry a `notices` list riding alongside the `offer` (per claude-klabauter's
coordinator_core/ops/deferral_detect_partial_strangle.py). Per the spec memo,
this trampoline renders `offer` only on that state -- it does not also print
the sibling `notices` on the found path.

Output: zero or one line of the form
  [health] deferral-partial-strangle: <message>
Exit 0 always (advisory, never gating).

Test seam (test-only): when COORDINATOR_DEFERRAL_PARTIAL_STRANGLE_JSON is set
and non-empty, its value is parsed AS the bare `result` dict payload directly
(mirrors the pre-existing seam contract: a `result` key is unwrapped, an
`error` key renders silent, and malformed JSON renders silent) -- the real
cc_invoke() call below is skipped entirely. This lets
check-deferral-partial-strangle.test.sh drive the rendering logic without a
live claude-klabauter checkout. The seam is checked BEFORE engine-root resolution so
tests do not need a real claude-klabauter checkout to exercise it.

Spec backlink: cross-repo/inbox/2026-07-21-claude-klabauter-em-deferral-detectors-workday-start.md

Negative-spec:
  - Does NOT write anything -- claude-klabauter's deferral.detect_partial_strangle op
    owns its own state.
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
    """Return the bare deferral.detect_partial_strangle result dict, or {} on
    any failure/skip.

    Test seam: COORDINATOR_DEFERRAL_PARTIAL_STRANGLE_JSON, when set and
    non-empty, supplies the bare result payload directly (same shape
    cc_invoke() would return on success) -- an "error" key or malformed JSON
    both degrade to {} (silent).
    """
    seam = os.environ.get("COORDINATOR_DEFERRAL_PARTIAL_STRANGLE_JSON", "")
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
        result = cc_invoke("deferral.detect_partial_strangle", {}, claude_klabauter_root)
    except RuntimeError:
        return {}
    return result if isinstance(result, dict) else {}


def main(argv: "list[str] | None" = None) -> int:
    del argv  # this CLI takes no arguments; argv accepted for the warm-call contract
    result = _fetch_result()
    state = result.get("state", "")

    if state == "partial_strangles_found":
        message = result.get("offer", "")
    elif state == "indeterminate":
        message = result.get("notice", "")
    else:
        return 0

    if message:
        print(f"[health] deferral-partial-strangle: {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
