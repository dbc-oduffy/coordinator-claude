# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""coordinator-workflow-scaffold.py — DoE-side veneer over the claude-klabauter
workflow.scaffold op.

Builds the workflow.scaffold params object (name, description, phases,
pattern) from CLI flags, dispatches it via coordinator/bin/lib/cc_invoke.py's
shared cc_invoke_bare() transport (--bare/--params-file), and writes the
returned Workflow skeleton `.script` text to --out or stdout. Does not
implement the skeleton-stamper engine itself — thin transport veneer only.
"""
# coordinator-workflow-scaffold.py — DoE-side veneer for the claude-klabauter workflow.scaffold op.
#
# Purpose: builds the workflow.scaffold params object from CLI flags, dispatches via
# the shared cc_invoke.py transport seam (cc_invoke_bare(), the --bare/--params-file
# convention), and writes the returned `.script` field to --out (or stdout when --out
# is omitted). This file does NOT re-implement the op contract or the
# workflow-skeleton-stamper engine itself — it is a thin transport veneer, same idiom
# as handoff-has-live-children.py's cc_invoke round-trip.
#
# Review: code-reviewer (P1) — this script used to carry a private hand-rolled
# _cc_invoke() that spawned `coordinator_core.invoke workflow.scaffold --bare
# --params-file <tmp> --repo <repo>` unconditionally. workflow.scaffold is a
# "none"-scoped op (coordinator_core/op_scopes.py), so DR-279's engine-side refusal
# (commit bd0e52a36154) made every invocation of this script fail loud with rc=1.
# Fixed by routing through cc_invoke.py's own cc_invoke_bare(), which already applies
# the DR-279-aware _should_pass_repo() gate on both its own spawn call sites — this
# closes the duplicate-transport drift instead of adding a third private copy of the
# scope check.
#
# Frozen op contract (producer-side, claude-klabauter):
#   Op: workflow.scaffold — COMPUTE_ONLY, returns text, does NOT write to disk.
#   Params: {"name": "<kebab-case>", "description": "<one-line>",
#            "phases": [{"title": "...", "detail": "..."}, ...],
#            "pattern": "<disk-poll-fanout|adversarial-verify|loop-until-dry|pipeline-default>"}
#   Returns: {"script": "<conformant Workflow skeleton text>"}
#
# Usage:
#   coordinator-workflow-scaffold.py --name <kebab> [--description "<line>"] \
#       [--title "<line>"] [--phase "Title::Detail"]... [--pattern <p>] \
#       [--out PATH]
#
#   --name         kebab-case workflow name (op `name`). Defaults to a slugified
#                  --title when --name is omitted but --title is given.
#   --title        Human-readable line; used as `description` fallback and as the
#                  --name slugify source when --name is absent.
#   --description  Op `description` (one-line). Overrides --title for `description`
#                  when both are given.
#   --phase        Repeatable. "Title::Detail" — split on the FIRST "::" only, so a
#                  Detail string containing "::" is preserved intact. Each becomes
#                  one {"title":..., "detail":...} entry in `phases[]`, in the order
#                  given on the command line.
#   --pattern      Op `pattern`. Defaults to pipeline-default (matches the harness's
#                  "DEFAULT TO pipeline()" convention) when omitted.
#   --repo         Refused: workflow.scaffold is a "none"-scoped op (see
#                  docs/decisions/DR-279-repo-on-a-none-scoped-op-fails-loud.md) —
#                  it accesses no repo-specific state, so --repo would be
#                  meaningless. Passing it fails loud instead of silently
#                  no-opping, matching DR-279's shape for the underlying op.
#   --out          Write result.script here. Omitted -> stdout.
#
# Exit codes:
#   0 — success; script text written to --out or stdout.
#   1 — bad args (missing --name/--title, missing --description/--title, malformed
#       --phase, --repo passed (DR-279 refusal), --out write failure).
#   2 — op/dispatch error: coordinator_core.invoke started and exited nonzero with
#       what looks like a JSON-RPC business/param error (e.g. missing name/description,
#       unknown pattern) rather than a transport failure. Stderr is printed verbatim —
#       this is NOT "claude-klabauter isn't ready," it's the op rejecting the given params.
#       Also covers empty stdout / unparseable invoke output / missing "script" key.
#   3 — genuine transport/engine failure: invoke timeout, ImportError/ModuleNotFoundError-
#       shaped stderr (engine won't import/start), or engine-root resolution failure.
#       (workflow.scaffold IS registered on claude-klabauter HEAD — see ops/__init__.py and
#       @register_op("workflow.scaffold") in workflow_scaffold.py; this exit code
#       does NOT imply the op is unshipped.)
#
# Spec backlink: pln-workflow-skeleton-stamper-maki-adab0d
#
# Negative-spec:
#   - Does NOT write to disk itself when --out is omitted (stdout only).
#   - Does NOT invent op params beyond the frozen four (name/description/phases/pattern).
#   - Does NOT fall back to a local skeleton template when the op is unavailable —
#     fails loud instead (the op is COMPUTE_ONLY and this veneer has no local copy
#     of the harness's Workflow-skeleton conventions to fall back to).
#   - Does NOT import coordinator_core.invoke in-process — it is spawned as a
#     subprocess (ARG_MAX-safe --params-file transport), same as the bash oracle.

from __future__ import annotations

import os
import re
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import (  # noqa: E402
    StructuralPinError,
    cc_invoke_bare,
    is_timeout_error,
    none_scoped_repo_refusal,
)

GENERATES = []  # writes only to the caller-supplied --out path (or stdout when omitted) — no fixed tracked artifact

_PROG = "coordinator-workflow-scaffold.py"


class _TransportError(Exception):
    """Raised on a genuine transport/engine failure — timeout, ImportError/
    ModuleNotFoundError-shaped stderr, engine-root resolution failure, empty
    stdout, or unparseable invoke output. Maps to exit 3.
    """


class _OpError(Exception):
    """Raised when coordinator_core.invoke started and exited nonzero with what
    looks like an op-level (business/param) error rather than a transport
    failure — the engine dispatched, the op rejected the params. Maps to exit 2;
    message carries the op's actual stderr verbatim.
    """


def _cc_invoke(op: str, params: dict, repo_root: str) -> dict:
    """Dispatch via cc_invoke.py's shared cc_invoke_bare() transport, reclassifying
    its single RuntimeError-shaped failure surface back into this script's own
    _TransportError (exit 3) vs _OpError (exit 2) exit-code contract.

    cc_invoke_bare() already applies the DR-279-aware _should_pass_repo() gate on
    its --repo argv (see its own docstring / _should_pass_repo in cc_invoke.py), so
    this veneer no longer needs — or carries — its own private spawn/scope logic.
    """
    try:
        return cc_invoke_bare(op, params, repo_root)
    except StructuralPinError as exc:
        # Non-self-healing structural contract-pin failure (engine rc=2) — surfaced
        # as an op-level failure (exit 2), same bucket the pre-port bash oracle and
        # this veneer's own rc==2-but-not-ImportError branch used.
        raise _OpError(str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        # cc_invoke_bare() raises a single RuntimeError type for both transport and
        # op-level failures; its message text is the discriminator (mirrors the
        # ImportError-vs-generic-rc classification the removed private ladder did).
        #
        # The timeout arm goes through `is_timeout_error`, cc_invoke's own sanctioned
        # discriminator, rather than a literal substring — that function anchors on
        # `_TIMEOUT_MESSAGE_PREFIX`, so it cannot drift out from under this classifier
        # the way `"engine timeout" in msg` could. The engine-root arm accepts BOTH
        # spellings on purpose: an in-flight rename is moving this fleet's prose from
        # `CLAUDE_KLABAUTER_ROOT` to engine-root wording, and matching only the old spelling
        # would silently reclassify a resolution failure (transport, exit 3) as an
        # op-level rejection (exit 2) the day that rename reaches cc_invoke's own
        # message text. Both spellings mean the same failure; neither is load-bearing
        # alone. (Review finding, s3-cli-callers, 618164b2e4ad.)
        if (
            "engine will not import/start" in msg
            or is_timeout_error(exc)
            or "CLAUDE_KLABAUTER_ROOT" in msg
            or "engine root" in msg
            or "engine-root" in msg
            or "empty stdout" in msg
            or "not valid JSON" in msg
        ):
            raise _TransportError(msg) from exc
        raise _OpError(msg) from exc


def _usage() -> str:
    return (
        f"  Usage: {_PROG} --name <kebab> [--description \"<line>\"] "
        "[--phase \"Title::Detail\"]... [--pattern <p>] [--out PATH]"
    )


def main(argv: list[str]) -> int:
    name = ""
    title = ""
    description = ""
    pattern = "pipeline-default"
    out_path = ""
    phases_raw: list[str] = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--name":
            name = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--title":
            title = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--description":
            description = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--phase":
            phases_raw.append(argv[i + 1] if i + 1 < len(argv) else "")
            i += 2
        elif arg == "--pattern":
            pattern = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--repo":
            # workflow.scaffold is scoped "none" (op_scopes.py); --repo is
            # meaningless for it and used to be required + isdir-validated,
            # for a value that was never transmitted (D2,
            # docs/plans/2026-08-20-a-refusal-cannot-exit-zero.md § C16).
            # Refuse loud instead, matching
            # coordinator-compute-layer-scaffold.py's reference shape.
            print(none_scoped_repo_refusal(_PROG, "workflow.scaffold"), file=sys.stderr)
            return 1
        elif arg == "--out":
            out_path = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            print(f"{_PROG}: unknown arg: {arg}", file=sys.stderr)
            print(_usage(), file=sys.stderr)
            return 1

    if not name and not title:
        print(f"{_PROG}: --name or --title is required", file=sys.stderr)
        return 1

    if not description and not title:
        print(f"{_PROG}: --description or --title is required", file=sys.stderr)
        return 1

    # --- Build params (mirrors the original inline python3 -c param-builder). ---
    if not name:
        slug = title.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
        name = slug or "unnamed-workflow"

    if not description:
        description = title

    phases = []
    for raw in phases_raw:
        if "::" not in raw:
            print(f'{_PROG}: malformed --phase (expected "Title::Detail"): {raw}', file=sys.stderr)
            print(f"{_PROG}: params JSON build failed — see the error printed above", file=sys.stderr)
            return 1
        ptitle, pdetail = raw.split("::", 1)
        phases.append({"title": ptitle, "detail": pdetail})

    params = {
        "name": name,
        "description": description,
        "phases": phases,
        "pattern": pattern,
    }

    # --- Dispatch via cc_invoke. workflow.scaffold IS registered on claude-klabauter HEAD
    # (ops/__init__.py eager-import + @register_op("workflow.scaffold") in
    # workflow_scaffold.py) — a failure here is a real transport problem or a
    # real op/param rejection, not an unshipped-engine condition. Surface the
    # actual failure verbatim rather than a canned "not ready yet" message. ---
    try:
        # workflow.scaffold is scoped "none" — cc_invoke_bare's
        # _should_pass_repo() gate suppresses forwarding --repo for it, so
        # this empty string is never read; see the --repo refusal above.
        result = _cc_invoke("workflow.scaffold", params, "")
    except _TransportError as exc:
        print(str(exc), file=sys.stderr)
        print(
            f"{_PROG}: transport/engine failure dispatching workflow.scaffold — "
            "see stderr above (timeout, engine-root resolution, or engine "
            "import failure).",
            file=sys.stderr,
        )
        return 3
    except _OpError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    script_text = result.get("script") if isinstance(result, dict) else None
    if script_text is None:
        print(f'{_PROG}: cc_invoke result missing "script" key', file=sys.stderr)
        print(f"{_PROG}: failed to extract .script from workflow.scaffold result", file=sys.stderr)
        return 2

    # Trailing-newline normalization is intentional: always append a newline
    # regardless of whether script_text was already newline-terminated by the
    # op's raw response — POSIX text-file hygiene, not a bug.
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(script_text + "\n")
        except OSError as exc:
            print(f"{_PROG}: failed to write to --out path: {out_path} ({exc})", file=sys.stderr)
            return 1
        print(out_path)
    else:
        sys.stdout.write(script_text + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
