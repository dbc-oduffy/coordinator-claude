# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))


def _bootstrap_engine() -> str:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke
    from cc_invoke import _resolve_claude_klabauter_root

    return _resolve_claude_klabauter_root()


def _no_console_kw() -> dict:
    claude_klabauter_root = _bootstrap_engine()
    import cc_invoke

    return cc_invoke._no_console_kw(claude_klabauter_root)


def _no_console_passthrough_kw() -> dict:
    """`_no_console_kw` for a child whose output must reach the operator.

    Console suppression alone makes the child bind its standard handles to the
    window-less console CREATE_NO_WINDOW allocates instead of inheriting this
    process's, so its output is lost. See
    `cc_invoke._no_console_passthrough_kw` for the mechanism.
    """
    claude_klabauter_root = _bootstrap_engine()
    import cc_invoke

    return cc_invoke._no_console_passthrough_kw(claude_klabauter_root)


def _default_cruft_sweep_bin() -> str:
    return os.path.join(_BIN_DIR, "cruft-sweep.py")


def _cruft_sweep_argv(cruft_sweep_bin: str) -> list[str]:
    """Build the invocation argv for ``cruft_sweep_bin``.

    Only a ``.cmd`` sibling is directly executable. Everything else this
    function can be handed — the shipped ``cruft-sweep.py`` default, the
    extensionless installed shim, an extensionless test double — fails a bare
    launch on BOTH platforms: CreateProcess raises WinError 193 ("%1 is not a
    valid Win32 application") and does not interpret ``#!`` lines, and POSIX
    refuses a source file carrying no exec bit. Route through this interpreter
    explicitly rather than depend on a ``.cmd`` sibling existing on disk for a
    path this function does not itself control.

    Negative-spec: the extension test must NOT be "extensionless only" and the
    platform test must NOT be ``os.name == "nt"`` only. Both narrowings were
    live here until 2026-08-16 and left the shipped default (``.py``, set by
    ``_default_cruft_sweep_bin``) on the bare-launch rung, so Step 1.5 raised
    WinError 193 on every Windows run and degraded to its non-blocking WARN —
    the sweep never once executed. Mirrors ``wsc-session-disposition.py``'s
    ``_session_claim_cli_argv``, which already cites this function as its
    precedent.

    Second negative-spec, and it pulls the OTHER way: "everything but a
    ``.cmd`` needs an interpreter" stopped being true on 2026-09-02, when the
    native-door cutover began installing an EXECUTABLE compiled image at the
    extensionless settings-home name this function's docstring already names
    as an accepted input. Handing that to an interpreter is the defect that
    took every ``git commit`` on a cut-over box down. The exec bit is the
    discriminator, checked at call time; POSIX only, since
    ``os.access(X_OK)`` is true for any existing file on Windows.
    """
    if os.path.splitext(cruft_sweep_bin)[1] == ".cmd":
        return [cruft_sweep_bin]
    if (
        os.name != "nt"
        and not cruft_sweep_bin.endswith(".py")
        and os.access(cruft_sweep_bin, os.X_OK)
    ):
        return [cruft_sweep_bin]
    return [sys.executable, cruft_sweep_bin]


def _default_state_root_script() -> str:
    return os.path.join(_BIN_DIR, "..", "lib", "coordinator-state-root.py")


def _cruft_sweep_log_path(state_root_script: str) -> str:
    _bootstrap_engine()
    from cc_invoke import child_env

    try:
        result = subprocess.run(
            [sys.executable, state_root_script, "--central"],
            capture_output=True,
            text=True,
            env=child_env(),
            **_no_console_kw(),
        )
        central_root = result.stdout.strip()
        if result.returncode == 0 and central_root:
            return os.path.join(central_root, "cruft-sweep-log.md")
    except OSError:
        pass
    return "cruft-sweep-log.md"


def run_cruft_sweep(
    cruft_sweep_bin: str | None = None,
    state_root_script: str | None = None,
    out=sys.stdout,
    err=sys.stderr,
) -> int:
    cruft_sweep_bin = cruft_sweep_bin or _default_cruft_sweep_bin()
    state_root_script = state_root_script or _default_state_root_script()

    try:
        result = subprocess.run(
            [*_cruft_sweep_argv(cruft_sweep_bin), "--class", "all", "--apply", "--quiet"],
            **_no_console_passthrough_kw(),
        )
        rc = result.returncode
    except OSError as exc:
        print(
            f"[workday-complete] WARN: cruft-sweep Step 1.5 could not be invoked "
            f"({exc}) (non-blocking)",
            file=err,
        )
        return 0

    if rc != 0:
        log_path = _cruft_sweep_log_path(state_root_script)
        print(
            "[workday-complete] WARN: cruft-sweep Step 1.5 exited non-zero "
            f"(non-blocking) — check {log_path}",
            file=err,
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="workday-complete-reconcile.py — Step 1.5 cruft-sweep dispatch."
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_cruft = sub.add_parser("cruft-sweep", help="Step 1.5: dispatch cruft-sweep --class all --apply --quiet")
    p_cruft.add_argument("--cruft-sweep-bin", default=None, help="Path to the cruft-sweep binary (default: co-located sibling).")
    p_cruft.add_argument("--state-root-script", default=None, help="Path to coordinator-state-root.py (default: co-located lib sibling).")

    return parser


def main(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)

    if args.subcommand == "cruft-sweep":
        return run_cruft_sweep(
            cruft_sweep_bin=args.cruft_sweep_bin,
            state_root_script=args.state_root_script,
        )

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
