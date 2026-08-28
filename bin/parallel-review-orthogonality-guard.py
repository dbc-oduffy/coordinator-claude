# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""parallel-review-orthogonality-guard.py — pre-dispatch guard + weekly-slice
snapshot ops for coordinator:parallel-code-review (DoE-claude
coordinator/skills/parallel-code-review/SKILL.md).

Two subcommands, both self-resolving (Path(__file__)-relative, no cwd
dependence for locating the sibling verify/freeze CLIs they wrap):

    guard [--chunk-manifest <tsv>]
        Fail-fast wrapper over the sibling
        verify-parallel-review-lens-orthogonality.py CLI. Runs it (static
        lens-domain-collision form with no args, or the runtime
        chunk-disjointness form when --chunk-manifest is given) and, on a
        non-zero exit, prints the matching refusal message the skill's two
        Pre-Flight Orthogonality Assertion fences used to hand-roll inline,
        then exits 1. On success, exits 0 silently. Distinct refusal wording
        per mode lets `/workweek-complete` tell a manifest-missing agent file
        apart from a chunk-partition overlap without re-deriving either
        message.

    snapshot --range <range> [--slice-prefix <prefix>] [--ts <TS>]
             [--repo-root <path>]
        Weekly-slice diff-freeze with a derived head-sha path. Computes a
        UTC timestamp (`--ts` overrides, for deterministic tests), builds
        `<slice-prefix>-<TS>` as the slice id (default prefix: "weekly"),
        creates `state/review-findings/<TS>/` under the resolved repo root,
        and invokes the sibling freeze-review-diff.py CLI with that slice id.
        freeze-review-diff.py writes `<slice-id>.diff` and
        `<slice-id>.head.sha` side by side under
        `state/review-trail/diffs/`; HEAD_SHA_PATH is derived from the
        printed `.diff` path by suffix substitution
        (`DIFF_PATH[:-len(".diff")] + ".head.sha"`), mirroring the skill's
        own `${DIFF_PATH%.diff}.head.sha` shell parameter expansion — this
        is a load-bearing NAME CONVENTION with freeze-review-diff.py, not an
        independent computation, so it stays correct only as long as that
        CLI keeps writing the two files under the same slice-id stem.
        Prints a single JSON object to stdout:
            {"findings_dir": "...", "weekly_slice_id": "...",
             "diff_path": "...", "head_sha_path": "..."}

Both subcommands invoke their sibling CLI via subprocess (not import) —
verify-parallel-review-lens-orthogonality.py and freeze-review-diff.py are
each independently-versioned, independently-tested CLIs with their own
argv/exit-code contracts; this guard is a thin caller, not a re-implementation.

Exit codes:
    guard    — 0 (passed) / 1 (assertion failed, refusal message printed) /
               2 (usage error) / whatever non-{0,1} code the wrapped CLI
               itself returns is passed through verbatim on stderr as a
               transport-failure note (see _run_verify).
    snapshot — 0 (JSON printed) / 1 (freeze-review-diff.py failed; its own
               stderr is surfaced verbatim) / 2 (usage error).

Negative-spec: does NOT resolve the engine root, does NOT source the
_cc_trusted/_cc_root plugin-root-trust preamble, and does NOT walk the
resolve-claude-klabauter-bin settings-home ladder — none of that applies here. This
CLI and the two sibling CLIs it wraps (verify-parallel-review-lens-
orthogonality.py, freeze-review-diff.py) already live side by side in THIS
repo's coordinator/bin/, so there is no cross-repo root to resolve; the
DoE-claude skill fence's entire guard preamble collapses to a plain
co-located subprocess call. See CLAUDE.local.md (DoE-claude) "The boilerplate
evaporates rather than needing translation."

Spec backlink: coordinator/skills/parallel-code-review/SKILL.md (DoE-claude)
  § Pre-Flight Orthogonality Assertion, § Snapshot
Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


_PROG = "parallel-review-orthogonality-guard.py"
_BIN_DIR = Path(__file__).resolve().parent

#: The .cmd launcher's own basename — used by `recover_windows_argv` to locate
#: where this invocation's own arguments begin within the raw `%CMDCMDLINE%`
#: capture. `snapshot --range` takes a git rev/range typed directly at the
#: CLI (e.g. the `sha^..sha` predecessor-range shape), which cmd.exe's `%*`
#: batch-parameter population silently strips a literal `^` from — see
#: `coordinator/bin/lib/raw_cmdline_recovery.py`'s module docstring. Refuses
#: on an unvouchable capture (coordinator-write-review-trail.py's C2
#: posture — this is a low-traffic weekly-gate CLI, not scoped-git-commit's
#: ~40-concurrent-session hot path).
_LAUNCHER_CMD_NAME = "parallel-review-orthogonality-guard.cmd"
_VERIFY_CLI = _BIN_DIR / "verify-parallel-review-lens-orthogonality.py"
_FREEZE_CLI = _BIN_DIR / "freeze-review-diff.py"

_STATIC_REFUSAL = "Lens-orthogonality assertion failed; refusing to dispatch."
_CHUNK_REFUSAL = "Chunk partitions are not disjoint by file-scope; refusing to dispatch."

#: The verify CLI's own terminal line for a failing STATIC check. `--chunk-manifest`
#: runs the static check FIRST and short-circuits on it (that CLI's § RUNTIME), so
#: mode alone does not identify which check refused — keying the refusal on the mode
#: told an operator their partitions overlapped when the manifest table was simply
#: missing, and the manifest was never opened.
_STATIC_FAILURE_MARKER = "Lens-orthogonality (static) check failed."


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    """
    Deliberate isolation boundary — do not convert to an in-process
    import. This is crash containment: runs an arbitrary
    reviewer-supplied argv, which must not be able to take this process
    down with it. Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)
    from coordinator_core.win_portability import no_console_creationflags

    return subprocess.run(
        [sys.executable, *argv],
        capture_output=True,
        text=True,
        **no_console_creationflags(),
    )


def _cmd_guard(args: argparse.Namespace) -> int:
    cli_argv = [str(_VERIFY_CLI)]
    if args.chunk_manifest:
        cli_argv += ["--chunk-manifest", args.chunk_manifest]

    proc = _run(cli_argv)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    if proc.returncode == 0:
        return 0

    static_failed = _STATIC_FAILURE_MARKER in (proc.stdout or "") + (proc.stderr or "")
    refusal = _STATIC_REFUSAL if static_failed or not args.chunk_manifest else _CHUNK_REFUSAL
    print(refusal, file=sys.stderr)
    return 1


def _cmd_snapshot(args: argparse.Namespace) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)
    from coordinator_core.git.repo_root import show_toplevel

    ts = args.ts or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    weekly_slice_id = f"{args.slice_prefix}-{ts}"

    repo_root_argv = ["--repo-root", args.repo_root] if args.repo_root else []
    if args.repo_root:
        repo_root = Path(args.repo_root)
    else:
        toplevel = show_toplevel()
        if not toplevel:
            print(f"{_PROG}: snapshot: cannot resolve git repo root from cwd", file=sys.stderr)
            return 1
        repo_root = Path(toplevel)

    findings_dir = repo_root / "state" / "review-findings" / ts
    findings_dir.mkdir(parents=True, exist_ok=True)

    freeze_argv = [
        str(_FREEZE_CLI),
        "--range",
        args.range_,
        "--slice-id",
        weekly_slice_id,
        *repo_root_argv,
    ]
    proc = _run(freeze_argv)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return 1

    diff_path = proc.stdout.strip()
    if not diff_path:
        print(f"{_PROG}: snapshot: freeze-review-diff.py printed no path", file=sys.stderr)
        return 1

    head_sha_path = (
        diff_path[: -len(".diff")] + ".head.sha" if diff_path.endswith(".diff") else diff_path + ".head.sha"
    )

    print(
        json.dumps(
            {
                "findings_dir": str(findings_dir),
                "weekly_slice_id": weekly_slice_id,
                "diff_path": diff_path,
                "head_sha_path": head_sha_path,
            }
        )
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=_PROG)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    guard_p = sub.add_parser(
        "guard",
        help="fail-fast lens-orthogonality assertion (static or --chunk-manifest)",
    )
    guard_p.add_argument("--chunk-manifest", dest="chunk_manifest", default="")
    guard_p.set_defaults(func=_cmd_guard)

    snapshot_p = sub.add_parser(
        "snapshot",
        help="weekly-slice diff-freeze with derived head-sha path",
    )
    snapshot_p.add_argument("--range", dest="range_", required=True)
    snapshot_p.add_argument("--slice-prefix", dest="slice_prefix", default="weekly")
    snapshot_p.add_argument("--ts", dest="ts", default="")
    snapshot_p.add_argument("--repo-root", dest="repo_root", default="")
    snapshot_p.set_defaults(func=_cmd_snapshot)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from raw_cmdline_recovery import UnsoundRawCmdlineTransport, recover_windows_argv

    try:
        _argv = recover_windows_argv(sys.argv[1:], _LAUNCHER_CMD_NAME)
    except UnsoundRawCmdlineTransport:
        print(
            f"{_PROG}: the invoking shell stripped characters from this "
            f'command line before this process started — run `python "'
            f'{_BIN_DIR / _PROG}" ...` instead.',
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(main(_argv))
