"""coordinator-compute-layer-scaffold.py — sibling-repo veneer over the claude-klabauter
compute_layer.scaffold op.

Builds the compute_layer.scaffold params object (mode, skill_name, verbs,
modules) from CLI flags, dispatches it via coordinator/bin/lib/cc_invoke.py's
shared cc_invoke_bare() transport (--bare/--params-file), and writes the
returned text (module_text for --emit, report for --check) to --out or
stdout. Does not implement the emitter or check-mode scorer itself — thin
transport veneer only, same idiom as coordinator-workflow-scaffold.py.

Frozen op contract (producer-side, claude-klabauter):
  Op: compute_layer.scaffold — COMPUTE_ONLY, returns text, does NOT write to
      disk (either mode).
  Params (mode=emit): {"mode": "emit", "skill_name": "<skill>",
                        "verbs": ["<verb>", ...]}
  Returns (mode=emit): {"module_text": "<composed producer skeleton text>"}
  Params (mode=check): {"mode": "check", "modules": ["<module>", ...]}
                        ("modules" omitted -> the op's own Sub-shape B default)
  Returns (mode=check): {"report": "<rendered conformance report text>"}

Usage:
  coordinator-compute-layer-scaffold.py --emit --skill-name <skill> \
      --verb <verb> [--verb <verb>]... [--out PATH]
  coordinator-compute-layer-scaffold.py --check [--module <module>]... \
      [--out PATH]

  --emit          Select mode=emit. Mutually exclusive with --check; exactly
                   one of the two is required.
  --check         Select mode=check. Mutually exclusive with --emit.
  --skill-name    Op `skill_name` (mode=emit only).
  --verb          Repeatable (mode=emit only). One CONSUMES_MANIFEST entry
                   per flag, in the order given.
  --module        Repeatable (mode=check only). One module name to score per
                   flag; omitted -> the op's own default set.
  --repo          Refused: compute_layer.scaffold is a "none"-scoped op (see
                   docs/decisions/DR-279-repo-on-a-none-scoped-op-fails-loud.md)
                   — it accesses no repo-specific state, so --repo would be
                   meaningless. Passing it fails loud instead of silently
                   no-opping, matching DR-279's shape for the underlying op.
  --out           Write the result text here. Omitted -> stdout.

Exit codes:
  0 — success; result text written to --out or stdout.
  1 — bad args (missing/conflicting --emit/--check, missing --skill-name or
      --verb for --emit, --repo passed (DR-279 refusal), --out write
      failure).
  2 — op/dispatch error: coordinator_core.invoke started and exited nonzero
      with what looks like a JSON-RPC business/param error (e.g. missing
      skill_name/verbs, unknown mode) rather than a transport failure.
      Stderr is printed verbatim. Also covers empty stdout / unparseable
      invoke output / missing result key for the selected mode.
  3 — genuine transport/engine failure: invoke timeout, ImportError/
      ModuleNotFoundError-shaped stderr (engine won't import/start), or
      engine-root resolution failure.

Spec backlink: pln-the-compute-layer-scaffolder-e-90d036 § C4

Negative-spec:
  - Does NOT write to disk itself when --out is omitted (stdout only).
  - Does NOT invent op params beyond the frozen set per mode.
  - Does NOT fall back to a local skeleton/scorer when the op is unavailable
    — fails loud instead (the op is COMPUTE_ONLY and this veneer has no
    local copy of either the emitter or the check-mode conformance clauses).
  - Does NOT import coordinator_core.invoke in-process — it is spawned as a
    subprocess (ARG_MAX-safe --params-file transport), same as
    coordinator-workflow-scaffold.py.
"""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import StructuralPinError, cc_invoke_bare  # noqa: E402

GENERATES = []  # writes only to the caller-supplied --out path (or stdout when omitted) — no fixed tracked artifact

_PROG = "coordinator-compute-layer-scaffold.py"


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
    its single RuntimeError-shaped failure surface into this script's own
    _TransportError (exit 3) vs _OpError (exit 2) exit-code contract.
    """
    try:
        return cc_invoke_bare(op, params, repo_root)
    except StructuralPinError as exc:
        raise _OpError(str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        if (
            "engine will not import/start" in msg
            or "engine timeout" in msg
            or "CLAUDE_KLABAUTER_ROOT" in msg
            or "empty stdout" in msg
            or "not valid JSON" in msg
        ):
            raise _TransportError(msg) from exc
        raise _OpError(msg) from exc


def _usage() -> str:
    return (
        f"  Usage: {_PROG} --emit --skill-name <skill> --verb <verb>... [--out PATH]\n"
        f"     or: {_PROG} --check [--module <module>]... [--out PATH]"
    )


def main(argv: list[str]) -> int:
    mode = ""
    skill_name = ""
    out_path = ""
    verbs: list[str] = []
    modules: list[str] = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--emit":
            if mode and mode != "emit":
                print(f"{_PROG}: --emit and --check are mutually exclusive", file=sys.stderr)
                return 1
            mode = "emit"
            i += 1
        elif arg == "--check":
            if mode and mode != "check":
                print(f"{_PROG}: --emit and --check are mutually exclusive", file=sys.stderr)
                return 1
            mode = "check"
            i += 1
        elif arg == "--skill-name":
            skill_name = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif arg == "--verb":
            verbs.append(argv[i + 1] if i + 1 < len(argv) else "")
            i += 2
        elif arg == "--module":
            modules.append(argv[i + 1] if i + 1 < len(argv) else "")
            i += 2
        elif arg == "--repo":
            # Review: coordinator:code-reviewer (P4) — compute_layer.scaffold is
            # scoped "none" (op_scopes.py); --repo is meaningless for it and used
            # to be silently accepted and dropped. Refuse loud instead, matching
            # DR-279's shape for the underlying op
            # (docs/decisions/DR-279-repo-on-a-none-scoped-op-fails-loud.md).
            print(
                f"{_PROG}: --repo is meaningless for compute_layer.scaffold "
                "(scope=\"none\"): this op accesses no repo-specific state and "
                "never reads repo_root, so --repo would silently no-op. Omit "
                "--repo. See "
                "docs/decisions/DR-279-repo-on-a-none-scoped-op-fails-loud.md.",
                file=sys.stderr,
            )
            return 1
        elif arg == "--out":
            out_path = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            print(f"{_PROG}: unknown arg: {arg}", file=sys.stderr)
            print(_usage(), file=sys.stderr)
            return 1

    if not mode:
        print(f"{_PROG}: exactly one of --emit or --check is required", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 1

    if mode == "emit":
        if not skill_name:
            print(f"{_PROG}: --skill-name is required with --emit", file=sys.stderr)
            return 1
        if not verbs:
            print(f"{_PROG}: at least one --verb is required with --emit", file=sys.stderr)
            return 1
        params = {"mode": "emit", "skill_name": skill_name, "verbs": verbs}
        result_key = "module_text"
    else:
        params: dict = {"mode": "check"}
        if modules:
            params["modules"] = modules
        result_key = "report"

    try:
        # compute_layer.scaffold is scoped "none" — cc_invoke_bare's
        # _should_pass_repo() gate suppresses forwarding --repo for it, so this
        # empty string is never read; see the --repo refusal above.
        result = _cc_invoke("compute_layer.scaffold", params, "")
    except _TransportError as exc:
        print(str(exc), file=sys.stderr)
        print(
            f"{_PROG}: transport/engine failure dispatching compute_layer.scaffold — "
            "see stderr above (timeout, engine-root resolution, or engine "
            "import failure).",
            file=sys.stderr,
        )
        return 3
    except _OpError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    text = result.get(result_key) if isinstance(result, dict) else None
    if text is None:
        print(f'{_PROG}: cc_invoke result missing "{result_key}" key', file=sys.stderr)
        return 2

    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
        except OSError as exc:
            print(f"{_PROG}: failed to write to --out path: {out_path} ({exc})", file=sys.stderr)
            return 1
        print(out_path)
    else:
        sys.stdout.write(text + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
