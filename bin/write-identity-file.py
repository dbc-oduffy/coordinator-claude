# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
write-identity-file.py — CLI trampoline over claude-klabauter's registered
"install.write_identity_file" op, via coordinator/bin/lib/cc_invoke.py.

Purpose: fold the two hand-rolled `mktemp ~/.claude/coordinator-identity.yaml.XXXXXX`
+ heredoc + `mv` fences in coordinator-claude's commands/install.md (lines 669
and 818 — one for `operator_name`, one for `engagement_posture`) into a single
trampoline call over the already-built, already-registered
coordinator_core.ops.write_identity_file op (atomic via locked_rmw,
merge-not-replace, idempotent — see that module's docstring for the full
contract). This script does NOT reimplement any of that logic — it only
resolves the engine root, builds the `fields` dict from argv, and invokes the op
via cc_invoke.

Usage:
    write-identity-file --claude-home <path> [--operator-name NAME]
                         [--engagement-posture POSTURE]

At least one of --operator-name / --engagement-posture must be given. Both
install.md call sites collapse to one invocation each (or, if both fields are
known at once, a single call setting both).

Exit codes:
    0 — op reported exit_code 0 (write succeeded, or idempotent no-op).
    1 — op reported exit_code 1 (op-level error; message on stderr), or usage
        error (missing --claude-home / no fields given).
    2 — transport failure (the engine root unresolved, cc_invoke raised
        RuntimeError) — distinguished from an op-level failure per the
        fleet's dedicated-transport-exit-code convention (see
        backfill-initiative-fk.py's header for the precedent).

Spec backlink: scratchpad/scout-D-claude-klabauter-sizing.md § Item 5 (install.md
operator-identity heredoc writes, install.md:653-661, 819-828).
Port target: coordinator_core.ops.write_identity_file (already built, eager-
registered — see coordinator_core/ops/__init__.py).

Negative-spec:
  - Does NOT write the identity file itself — all writing happens inside
    coordinator_core.ops.write_identity_file via locked_rmw. This script is
    argv-to-JSON-RPC plumbing only.
  - Does NOT default --claude-home to os.environ — the caller (install.md
    fence) resolves ${CLAUDE_HOME:-$HOME} itself and passes the resolved
    value, matching the op's own contract (see write_identity_file.py's
    Params docstring).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

_EXIT_TRANSPORT_FAILURE = 2


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="write-identity-file",
        description="Write/merge fields into ~/.claude/coordinator-identity.yaml via claude-klabauter.",
    )
    parser.add_argument("--claude-home", required=True, metavar="PATH")
    parser.add_argument("--operator-name", default=None, metavar="NAME")
    parser.add_argument("--engagement-posture", default=None, metavar="POSTURE")
    args = parser.parse_args(argv)

    fields: dict[str, str] = {}
    if args.operator_name is not None:
        fields["operator_name"] = args.operator_name
    if args.engagement_posture is not None:
        fields["engagement_posture"] = args.engagement_posture

    if not fields:
        print(
            "write-identity-file: at least one of --operator-name / "
            "--engagement-posture is required",
            file=sys.stderr,
        )
        return 1

    from cc_invoke import _resolve_claude_klabauter_root, cc_invoke  # noqa: E402

    try:
        claude_klabauter_root = _resolve_claude_klabauter_root()
    except RuntimeError as exc:
        print(f"write-identity-file: engine-root resolution failed: {exc}", file=sys.stderr)
        return _EXIT_TRANSPORT_FAILURE

    params = {"claude_home": args.claude_home, "fields": fields}

    try:
        result = cc_invoke("install.write_identity_file", params, claude_klabauter_root)
    except RuntimeError as exc:
        print(f"write-identity-file: transport failure: {exc}", file=sys.stderr)
        return _EXIT_TRANSPORT_FAILURE

    if not isinstance(result, dict):
        print(
            f"write-identity-file: op returned non-dict result: {result!r}",
            file=sys.stderr,
        )
        return _EXIT_TRANSPORT_FAILURE

    exit_code = result.get("exit_code", 1)
    if exit_code == 0:
        print(result.get("message", json.dumps(result)))
        return 0

    print(f"write-identity-file: {result.get('error', 'unknown op error')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
