# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""emit-cockpit-snapshot.py — native Python entry routing artifact.emit.

Purpose: pure-Python replacement for the retired bash strangler facade.
Dispatches the cockpit snapshot emission
through claude-klabauter's `artifact.emit` op via `cc_invoke.route_mutation()`
(coordinator/bin/lib/cc_invoke.py) — no shell, no bash re-exec, no local
mirror of the transport ladder.

2026-07-19 Windows de-bash campaign (Wave 1b, B-facade repoint). The
original bash body was already a fail-loud stub with no working emitter
(DR-208 ported the real emitter to claude-klabauter's Python `artifact.emit`;
DR-210 collapsed the bash body to a State-1 fallback that only raises) —
this port carries that same routing contract forward natively, updated for
the same-day W0.5 ruling (claude-klabauter is a mandatory dependency in every
environment; cc_invoke.route()/route_mutation() now wrap ANY State-1
legacy_fn failure in one standardized four-rung remediation message — see
cc_invoke.py's `_state1_remediation_message`) — so State-1 and State-3 are
both genuine broken-install/broken-op fail-loud outcomes, collapsed to one
exit code (parity with the sibling W0.5 ports):

  State 1 (seam absent on disk)       -> legacy_emit() raises; cc_invoke.route_mutation()
                                          wraps it in the standardized remediation message.
  State 2 (seam present, op succeeds) -> native result printed to stdout, exit 0.
  State 3 (seam present, transport/op failure) -> fail loud, same exit code as State 1.

Spec backlink: docs/plans/2026-07-08-retire-js-cockpit-emitter-lockstep.md § D1 (Option 2)
Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § Wave 1 (Category B)
Prior backlink: docs/plans/2026-07-04-strang-01-tc3-emission-port-facade-respin.md § C2
Prior backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C5

Usage (unchanged from the pre-port bash body — zero caller-arg repoints):
    python3 emit-cockpit-snapshot.py
    python3 emit-cockpit-snapshot.py --out /path/to/output.json

Exit codes:
    0 — success, native artifact.emit result printed to stdout.
    1 — fail-loud: State-1 (seam absent, standardized remediation message) OR
        State-3 (native transport/op-level failure, post-spawn).

Negative-spec: does NOT invoke bash, sh, or any shell — subprocess spawning
lives entirely inside cc_invoke.route_mutation() (sys.executable argv list,
never a shell string). No local `--bare` ladder mirror: this module imports
`route_mutation` from `coordinator/bin/lib/cc_invoke.py` (Wave 1a shared
helper) rather than inlining its own transport plumbing.
"""
from __future__ import annotations

import json
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402
import halted_marker  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402


def legacy_emit() -> None:
    """State-1 fallback — the claude-klabauter control-plane seam is absent on disk.

    The cockpit emitter was ported to claude-klabauter's Python `artifact.emit` (DR-208
    tri-plane relocation); this entry carries no fallback emitter body. Raises
    unconditionally; cc_invoke.route_mutation() wraps this in the standardized
    four-rung remediation message (W0.5) rather than propagating this raw text.

    Spec: docs/plans/2026-07-08-retire-js-cockpit-emitter-lockstep.md § D1 (Option 2)
    """
    raise RuntimeError("emit-cockpit-snapshot: native seam required (no bash fallback -- big-bang cutover)")


def _resolve_repo_root() -> str:
    """Resolve the repo root via the checked resolver (coordinator/bin/lib/repo_identity.py).

    WRITER script: this entry mutates the resolved repo (artifact.emit), so a
    positive MISMATCH refuses before any write lands -- the DR-277 carve-out
    ("prevents a write into a foreign tree") is what licenses the hard deny
    here. UNRESOLVED never refuses (DR-277, AC4) -- a degenerate/absent
    anchor must not turn this into a fleet-wide outage.
    """
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
        sys.exit(1)
    if not root:
        # No git root resolved from cwd at all -- distinct from the
        # MISMATCH identity gate above (positive evidence of a DIFFERENT
        # real repo). This is "nowhere to write"; refusing here is not the
        # AC4 "UNRESOLVED never refuses" carve-out being violated.
        print(
            f"emit-cockpit-snapshot: cannot resolve git repo root from {os.getcwd()}",
            file=sys.stderr,
        )
        sys.exit(1)
    return root


def _parse_args(argv: list[str]) -> dict[str, object]:
    """Build the artifact.emit params dict from CLI args.

    Mirrors the pre-port bash body's contract: `--out <path>` maps to
    params.out (artifact_emit.py § Params). Any other/unrecognized token is
    ignored (parity with the bash body's jq-only `--out` handling).
    """
    params: dict[str, object] = {}
    i = 0
    n = len(argv)
    while i < n:
        if argv[i] == "--out" and i + 1 < n:
            params["out"] = argv[i + 1]
            i += 2
        else:
            i += 1
    return params


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    params = _parse_args(argv)
    repo_root = _resolve_repo_root()

    try:
        result = cc_invoke.route_mutation("artifact.emit", params, repo_root, legacy_emit)
    except cc_invoke.RouteMutationError as exc:
        print(json.dumps(exc.result) if isinstance(exc.result, dict) else str(exc), file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # The DR-287 halt marker sits beside the canonical artifact and stamps the
    # `emitted_at` it was written against. An on-demand emission advances the
    # artifact without touching the marker, so the stamp would lag the bytes
    # until the next ceremony close in this repo happened to re-sync it —
    # a consumer bridging on this entry point (example-cockpit-repo's pre-`store:build`
    # invocation, DR-287 § Open direction) would read a stale stamp over fresh
    # data. Re-stamp, never remove: the cadence is still halted, the artifact
    # advanced because somebody asked. Skipped under `--out`, which writes
    # somewhere the marker does not describe.
    if "out" not in params:
        halted_marker.sync_halted_marker(repo_root)

    # STDOUT PASSTHROUGH (parity with the bash oracle's cc_invoke stdout
    # pass-through): the bare native result is re-emitted on stdout.
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
