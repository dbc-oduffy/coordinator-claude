# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""handoff-stamp-phase.py — CLI trampoline over claude-klabauter's `handoff.stamp_phase`
op, the sibling landed entrypoint `handoff-archive-transition.py` did not yet
cover.

Purpose: this file closes the documented DoE `/handoff` SKILL.md known-gap
note (the op was "native-seam-only ... invoked ad-hoc at the operator's own
shell") by giving `handoff.stamp_phase` (`coordinator_core/ops/
handoff_phase_stamp.py`) a landed CLI, same named-entrypoint treatment as
`handoff-archive-transition.py`. Stamps `handoff_phase: {continuation|
execution}` onto a target `state/handoffs/*.md` baton and, when
`phase=execution`, the four `execution_authorized_{by,at,sha,note}` fields
read from the cited plan's own frontmatter (the op's sole v1 value-source —
see the op's own module docstring, Decision D1).

CLI surface:

    handoff-stamp-phase.py <handoff-path> --phase {continuation|execution}
        [--plan-path <path>]

    <handoff-path>   positional; absolute path to the target state/handoffs/*.md
                     baton. A relative path is resolved against the invoking
                     process's CWD (os.path.abspath), NOT against any target
                     repo — pass absolute paths for cross-repo invocation.
    --phase          required; "continuation" or "execution".
    --plan-path      required when --phase=execution (ignored otherwise);
                     absolute or repo-relative path to the plan whose
                     frontmatter carries the four execution_authorized_*
                     fields. Rejected here (exit 2, before the op is even
                     invoked) when --phase=execution and --plan-path is
                     absent/empty — the op ALSO enforces this at its own
                     layer, but a clean pre-op usage error is better
                     ergonomics than a round-trip through the engine just to
                     learn the same thing (mirrors how the sibling
                     handoff-archive-transition.py's `supersede` subcommand
                     rejects a missing --continued-into up front).

Repo-root resolution (the load-bearing fix this port exists for): resolves
the confinement root from the TARGET HANDOFF'S OWN DIRECTORY
(`git -C <dirname(handoff_path)> rev-parse --show-toplevel`) — same technique
as handoff-archive-transition.py's `_resolve_repo_root` — rather than from the
process cwd. This is what lets a settings-home forwarder invoke this CLI
against a *consumer* repo's handoff (e.g. a DoE-claude EM stamping their own
baton): the confinement root is the target handoff's worktree, not whatever
repo this CLI happens to be invoked from. `handoff.stamp_phase` is a
common_dir-scoped op (see the op's own P9 docstring note); this CLI passes
the resolved worktree TOPLEVEL as --repo, unchanged from the sibling's
convention — the engine's own `_origin_worktree` -> `git_common_dir()`
derivation (coordinator_core/ipc.py) is what turns that toplevel into the
`<worktree>/.git` common_dir the op handler actually receives. This CLI does
NOT compute or pass a `.git` path itself.

Behavior parity: thin trampoline over the op — no new logic. The op already
owns the `kind == session-handoff` pre-write guard, the post-mutation
`validate_frontmatter()` gate, and D1 full-target-state idempotency; none of
that is duplicated or reimplemented here.

Exit codes:
    0 — op succeeded (stamped, or an already-converged idempotent no-op).
    1 — op-level refusal (RouteMutationError) or transport/engine failure, or
        an unresolvable repo root.
    2 — usage error (missing/invalid --phase, missing handoff-path, or
        --phase=execution with no --plan-path).

Negative-spec:
    - Does NOT open any UDS socket or read an auth token — routes through
      cc_invoke.route_mutation(), a command-type transport (fresh
      coordinator_core.invoke subprocess per call), same as every other bin/
      CLI in this house style.
    - Does NOT read/parse the plan's execution_authorized_* fields itself —
      that stays the op's exclusive job (plan_path is passed through as an
      opaque param).
    - Does NOT touch handoff.archive_transition or any archival/supersession
      concern — that stays handoff-archive-transition.py's job.
    - Does NOT recompute or validate execution_authorized_sha — reads/copies
      it as an opaque string, entirely inside the op (out of this CLI's
      reach).

Spec backlink: DoE-claude coordinator/skills/handoff/SKILL.md's
    "native-seam-only ... invoked ad-hoc" known-gap note; originating memo
    cross-repo/inbox/2026-07-24-doe-claude-em-handoff-stamp-phase-cli-gap.md.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
import cc_invoke  # noqa: E402

PROG = "handoff-stamp-phase.py"


def _no_console_kw() -> dict:
    """Lazily resolve the engine root onto sys.path (self-location-first via
    cc_invoke.ensure_engine_on_path — see that function's docstring), then
    splat the canonical no-console-window kwarg. ``{}`` on any resolution/
    import failure (fail-open)."""
    try:
        if cc_invoke.ensure_engine_on_path(__file__) is None:
            return {}
        from coordinator_core.win_portability import no_console_creationflags

        return no_console_creationflags()
    except Exception:
        return {}


# Duplicated from coordinator_core/ops/handoff_phase_stamp.py's own
# _VALID_PHASES on purpose: this local tuple drives argparse's `choices=`,
# giving a fast pre-op exit-2 usage error instead of a round-trip through the
# engine. Keep in sync with the op's tuple if a phase value is ever added.
_VALID_PHASES = ("continuation", "execution")


def _no_fallback():
    raise RuntimeError(
        f"{PROG}: handoff.stamp_phase requires the native seam (no bash "
        "fallback -- big-bang cutover); re-run coordinator:install or verify "
        "CLAUDE_KLABAUTER_ROOT"
    )


def _resolve_repo_root(handoff_path: str) -> str | None:
    """Resolve repo root from the handoff's own directory, not the process cwd.

    Mirrors handoff-archive-transition.py's `_resolve_repo_root` technique —
    candidate-dir discovery always resolves the correct per-repo git root
    regardless of where this CLI happens to be invoked from. This is the
    load-bearing behavior for the cross-repo case this port exists to cover
    (see module docstring).
    """
    handoff_abs = os.path.abspath(handoff_path)
    try:
        proc = subprocess.run(
            ["git", "-C", os.path.dirname(handoff_abs), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            **_no_console_kw(),
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return root or None


def cmd_stamp_phase(handoff_path: str, phase: str, plan_path: str | None) -> int:
    repo_root = _resolve_repo_root(handoff_path)
    if not repo_root:
        print(
            f"handoff-stamp-phase: cannot resolve git repo root from "
            f"{handoff_path!r}'s directory",
            file=sys.stderr,
        )
        return 1

    params: dict = {"handoff_path": handoff_path, "phase": phase}
    if phase == "execution":
        params["plan_path"] = plan_path

    try:
        result = cc_invoke.route_mutation(
            "handoff.stamp_phase", params, repo_root, _no_fallback
        )
    except cc_invoke.RouteMutationError as exc:
        print(f"ERROR: handoff.stamp_phase failed: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"ERROR: handoff.stamp_phase failed: {exc}", file=sys.stderr)
        return 1

    if isinstance(result, dict):
        message = result.get("message")
        if message:
            print(message, file=sys.stderr)

    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=PROG)
    p.add_argument("handoff_path")
    p.add_argument(
        "--phase",
        required=True,
        choices=_VALID_PHASES,
        help="handoff_phase value to stamp",
    )
    p.add_argument(
        "--plan-path",
        dest="plan_path",
        default=None,
        help="plan whose frontmatter carries the four execution_authorized_* "
        "fields; required when --phase=execution, ignored otherwise",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    if args.phase == "execution" and not (args.plan_path and args.plan_path.strip()):
        print(
            f"{PROG}: --phase=execution requires a non-empty --plan-path "
            "(sole v1 value-source for the execution_authorized_* stamp — "
            "see this file's module docstring)",
            file=sys.stderr,
        )
        return 2

    return cmd_stamp_phase(args.handoff_path, args.phase, args.plan_path)


if __name__ == "__main__":
    sys.exit(main())
