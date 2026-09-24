# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
workday-complete-close.py -- late-ceremony orchestration logic for /workday-complete
(the tail of the ceremony: Step 4d observer-sidecar stitch, Step 9's changelog-append
dispatch gate, Step 10.5's post-ceremony command hook, and Step 10.6's emission-cadence
rc dispatch).

Purpose: these four steps each wrap an ALREADY-native sibling CLI
(stitch-observer-sidecar.py, workday-complete-step9-append-changelog.py,
coordinator-ceremony-hook.py, emit-cadence.py) with a small amount of genuine
imperative logic -- path construction, `--only`-mode gating, and exit-code-to-message
dispatch ladders -- that was still living as inline bash in DoE-claude's
commands/workday-complete.md. This CLI concentrates that residual logic into one
naked-Python, idempotent, self-resolving entrypoint so the DoE ceremony body can
call it by subcommand name instead of carrying the bash.

This file does NOT re-implement any of the four sibling CLIs' own logic -- it only
constructs their arguments/paths, invokes them as subprocesses (matching how the bash
oracle invoked them), and translates their exit codes into the same diagnostic
messages / hard-fail-vs-non-blocking decisions the bash oracle made.

Subcommands:
  stitch-sidecar [--today YYYY-MM-DD]
      Step 4d. Computes MACHINE (coordinator_core.machine_resolver.compute_machine)
      and TODAY (coordinator_core.daily_day.local_day, unless --today overrides),
      derives the daily-summary and observer-sidecar paths, and invokes
      stitch-observer-sidecar.py against them. A non-zero exit from the sidecar
      stitcher is a HARD FAIL here (exit 1) -- the sidecar is left in place and the
      caller must NOT re-run blind (mirrors the bash oracle's `exit 1` on
      `_stitch_rc != 0`, DoE workday-complete.md Step 4d).

  step9-dispatch [SCOPE_SUMMARY] [--only-mode] [--no-push] [--dry-run]
                 [--commit-span RANGE] [--for-date DATE]
      Step 9's dispatch gate. Under `--only-mode` (DoE `$_ONLY_MODE=1`), the
      today-scoped changelog block is a no-op -- prints the skip note and returns 0
      without invoking the changelog-append CLI at all (the targeted block was
      already written via Step 3.5 Phase B). Otherwise forwards SCOPE_SUMMARY and
      the pass-through flags to workday-complete-step9-append-changelog.py, with
      RC_VALIDATE/RC_PLUGIN_SUITE defaulted ("not-run"/"n/a") when the calling
      ceremony hasn't set them, and returns that script's own exit code verbatim.

  ceremony-hook [--only-mode]
      Step 10.5. Under `--only-mode`, prints the skip note and returns 0 without
      invoking the hook. Otherwise invokes coordinator-ceremony-hook.py
      workday-complete, captures its one-line stdout contract, re-emits it verbatim
      if non-empty, and WARNs (non-blocking) on a non-zero exit -- the hook itself
      is a always-exit-0 contract (see that script's own docstring); this guard is
      defensive-only against the sibling script being absent/unexecutable
      (install-drift), not against the hook's own business logic ever failing.
      Always returns 0 -- the post-ceremony hook must never block the ceremony.

  backfill-dispatch-rows [--for-date DATE] [--only-mode] [--scope-summary TEXT]
                         [--no-push] [--dry-run]
      Step 3.5 Phase B. Reads the full gap-rows blob on stdin (one
      `<date>\\t<commit_count>\\t<base>\\t<tip>` row per line, blank lines
      ignored -- the shape workday-complete-backfill-scan.py emits) and
      dispatches step9-dispatch once per row, oldest-first as given. Per row:
      builds `--commit-span <base>..<tip>` only when both base and tip are
      non-empty (legacy rows without a well-formed span omit the flag);
      forwards `--scope-summary` as the bare SCOPE_SUMMARY positional only for
      the row matching `--for-date` (auto-detected rows carry no user-supplied
      prose); under `--only-mode`, skips every row whose date does not equal
      `--for-date` without dispatching. After the loop, if `--for-date` was
      given but never matched a row, prints the non-error
      "not detected as a gap" INFO note. Returns 0 only if every dispatched
      row's step9-dispatch also returned 0 (a non-zero row is reported to
      stderr and the loop continues -- one bad day should not abandon the
      rest of the backfill).

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (Windows de-bash
    campaign, M3 chunk WDC-4)
Spec backlink: commands/workday-complete.md (DoE-claude) § Step 4d / Step 9 /
    Step 10.5 / Step 10.6 -- the bash this file replaces; the DoE repoint (D2) is a
    later wave and is out of scope for this port.
Prior bash form: see DoE-claude git history for commands/workday-complete.md's
    inline Step 4d / Step 9 dispatch / Step 10.5 / Step 10.6 blocks (this port lifts
    that logic out; the DoE file itself is not edited here).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent

_STITCH_SIDECAR_CLI = _BIN_DIR / "stitch-observer-sidecar.py"
_STEP9_CLI = _BIN_DIR / "workday-complete-step9-append-changelog.py"
_CEREMONY_HOOK_CLI = _BIN_DIR / "coordinator-ceremony-hook.py"

# Per-gap-date backfill dispatch (_dispatch_step9_row) invokes the entire
# composed step9 ceremony once per row with NO bound at all — on this repo's
# 50-70-concurrent-session load norm an unbounded spawn here can wedge a
# ceremony with no session available to fix it (state/audits/
# 2026-08-15-fleet-composed-op-spawn-census.md row 14). step9-append-changelog
# itself bounds its OWN internal subprocess calls at 15-30s each but runs
# several of them sequentially plus a possible git push; 120s gives that
# composed chain headroom without being unbounded.
_STEP9_ROW_DISPATCH_TIMEOUT_SECS = 120


def _bootstrap_engine() -> None:
    """Put `coordinator/bin/lib` on `sys.path` and resolve the co-located
    engine root -- the same two-step sequence `main()` runs before
    dispatching any subcommand. Called again, idempotently, from each
    function below that does its own deferred `coordinator_core`/`cc_invoke`
    import, so an in-process caller that reaches one of them directly
    (bypassing `main()`) is not left with an un-bootstrapped `sys.path`."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)


def _load_sibling_module(cli_path: Path, module_name: str):
    """Import a sibling coordinator/bin CLI by path, in-process."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, cli_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_stitch_sidecar(args: argparse.Namespace) -> int:
    """Step 4d: stitch the Sonnet daily observer's sidecar into the canonical
    daily summary, hard-failing (never silently proceeding) on a non-zero exit
    from the sidecar stitcher.

    P055-C1 conversion: was a `[python, _STITCH_SIDECAR_CLI, *args]` spawn via
    the (now-removed) generic `_run` helper. stitch-observer-sidecar.py's own
    `main(argv)` indexes `argv[0]` as its own prog name (its `__main__` guard
    calls `main(sys.argv)`, not `sys.argv[1:]`), so the in-process call below
    passes a placeholder prog-name element to match that contract exactly.
    """
    _bootstrap_engine()
    from coordinator_core.daily_day import local_day
    from coordinator_core.machine_resolver import compute_machine

    machine = compute_machine()
    today = args.today or local_day()
    daily_summary = f"archive/daily-summaries/{today}-{machine}.md"
    observer_sidecar = f"archive/daily-summaries/{today}-{machine}.observer.md"

    stitch = _load_sibling_module(_STITCH_SIDECAR_CLI, "stitch_observer_sidecar")
    rc = stitch.main(["stitch-observer-sidecar.py", daily_summary, observer_sidecar])
    if rc != 0:
        print(
            f"ERROR: stitch-observer-sidecar failed (rc={rc}) — "
            "see stderr above. The sidecar was left in place; do NOT re-run this "
            "step blind. Investigate before continuing /workday-complete.",
            file=sys.stderr,
        )
        return 1
    return 0


def _load_step9_module():
    """Import workday-complete-step9-append-changelog.py by path, in-process.

    P055-C1 conversion (shared by `cmd_step9_dispatch` and
    `_dispatch_step9_row`, both of which were `[python, _STEP9_CLI, *forward]`
    spawns): its own `main(argv)` reads `argv[1:]`-shaped input (confirmed by
    its own `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`), so
    `forward` below needs no prog-name prefix -- the same shape the spawn
    form already built.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("workday_complete_step9_append_changelog", _STEP9_CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cmd_step9_dispatch(args: argparse.Namespace) -> int:
    """Step 9's dispatch gate: skip entirely under --only-mode (the targeted
    block was already committed via Step 3.5 Phase B), otherwise forward to
    workday-complete-step9-append-changelog.py with RC_VALIDATE/RC_PLUGIN_SUITE
    defaulted from the environment."""
    _bootstrap_engine()

    if args.only_mode:
        print(
            "[workday-complete] --only set — skipping today-scoped Step 9 "
            "(targeted wrap already committed via Step 3.5 Phase B)",
            file=sys.stderr,
        )
        return 0

    forward: list[str] = []
    if args.no_push:
        forward.append("--no-push")
    if args.dry_run:
        forward.append("--dry-run")
    if args.commit_span:
        forward.extend(["--commit-span", args.commit_span])
    if args.for_date:
        forward.extend(["--for-date", args.for_date])
    if args.scope_summary:
        forward.append(args.scope_summary)

    # In-process now, so these are this process's own env, not a child's --
    # matches the spawn form's setdefault-on-a-copy semantics for THIS run
    # (never overwrites an already-set value; both keys are process-lifetime,
    # exactly as they were per-child before).
    os.environ.setdefault("RC_VALIDATE", "not-run")
    os.environ.setdefault("RC_PLUGIN_SUITE", "n/a")

    step9 = _load_step9_module()
    return step9.main(forward)


def cmd_ceremony_hook(args: argparse.Namespace) -> int:
    """Step 10.5: run the generic post-ceremony command hook, non-blocking on
    any failure (the hook's own contract is always-exit-0; a non-zero exit here
    means the sibling script itself couldn't be found/exec'd -- install drift,
    not a business failure)."""
    if args.only_mode:
        print(
            "[workday-complete] --only set — skipping post-ceremony command hook",
            file=sys.stderr,
        )
        return 0

    # P055-C1 conversion: was a `[python, _CEREMONY_HOOK_CLI, "workday-complete"]`
    # spawn via the (now-removed) generic `_run` helper. coordinator-ceremony-hook.py's
    # own `__main__` guard wraps `main(sys.argv[1:])` in a broad try/except so an
    # unanticipated escape still honors its "always exit 0" contract -- that backstop
    # lived OUTSIDE `main()` itself, so calling `main()` directly here does not inherit
    # it. Recreated locally: this call site's OWN contract is already "never blocks",
    # so any exception maps to the same non-blocking WARN path a nonzero rc took.
    import contextlib
    import io

    _bootstrap_engine()
    ceremony_hook = _load_sibling_module(_CEREMONY_HOOK_CLI, "coordinator_ceremony_hook")
    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            rc = ceremony_hook.main(["workday-complete"])
    except Exception:
        rc = 1
    if rc != 0:
        print(
            "[workday-complete] WARN: ceremony-hook exited non-zero (non-blocking)",
            file=sys.stderr,
        )
    hook_out = stdout_buf.getvalue().strip()
    if hook_out:
        print(hook_out)
    return 0


def _dispatch_step9_row(
    date: str,
    span_flag: str | None,
    scope_arg: str | None,
    no_push: bool,
    dry_run: bool,
) -> int:
    """Invoke step9-dispatch for a single backfill row and return its exit
    code verbatim (RC_VALIDATE/RC_PLUGIN_SUITE defaulted, matching
    cmd_step9_dispatch's non---only-mode forward path)."""
    _bootstrap_engine()
    from coordinator_core.win_portability import no_console_passthrough_kwargs

    forward = ["--for-date", date]
    if span_flag:
        forward.extend(["--commit-span", span_flag])
    if no_push:
        forward.append("--no-push")
    if dry_run:
        forward.append("--dry-run")
    if scope_arg:
        forward.append(scope_arg)

    env = dict(os.environ)
    env.setdefault("RC_VALIDATE", "not-run")
    env.setdefault("RC_PLUGIN_SUITE", "n/a")

    try:
        result = subprocess.run(
            [sys.executable, str(_STEP9_CLI), *forward],
            env=env,
            timeout=_STEP9_ROW_DISPATCH_TIMEOUT_SECS,
            **no_console_passthrough_kwargs(),
        )
    except subprocess.TimeoutExpired:
        # A timed-out row must fail THIS row only, never abort the rest of
        # the backfill loop (cmd_backfill_dispatch_rows' per-row isolation
        # contract — "one bad day should not abandon the rest").
        print(
            f"ERROR: backfill-dispatch-rows: step9-dispatch timed out after "
            f"{_STEP9_ROW_DISPATCH_TIMEOUT_SECS}s for {date}",
            file=sys.stderr,
        )
        return 1
    return result.returncode


def cmd_backfill_dispatch_rows(args: argparse.Namespace) -> int:
    """Step 3.5 Phase B: parse the stdin gap-rows blob and dispatch step9
    once per row, oldest-first as given. See the module docstring's
    `backfill-dispatch-rows` entry for the per-row flag-building and
    --only-mode skip rules this ports from workday-complete.md's Phase B
    paragraph."""
    raw = sys.stdin.read()
    if not raw.strip() and not args.allow_empty:
        # The defect this command was reported for: empty stdin produced zero
        # rows, the dispatch loop never ran, and it returned 0 — a clean
        # success in the ceremony report while nothing had been written. The
        # scan emits NOTHING for a gapless window, so "" cannot be told from
        # "stdin was never wired" at this seam. `--allow-empty` moves that
        # discrimination to the caller: apply passes it because `stdin_from`
        # has already proved the producer landed, so empty genuinely means no
        # gaps. A hand or mis-wired invocation without it fails loud instead.
        print(
            "ERROR: backfill-dispatch-rows: no gap rows on stdin. Pipe "
            "workday-complete-backfill-scan's output in, or pass --allow-empty "
            "if a gapless window is the expected result.",
            file=sys.stderr,
        )
        return 1
    rows: list[tuple[str, str, str]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 4:
            print(
                f"WARN: malformed gap row (expected 4 tab-separated fields, "
                f"got {len(fields)}): {line!r} -- skipping",
                file=sys.stderr,
            )
            continue
        date, _commit_count, base, tip = fields[0], fields[1], fields[2], fields[3]
        rows.append((date, base, tip))

    processed_dates: set[str] = set()
    overall_rc = 0

    if args.only_mode and not args.for_date:
        print(
            "ERROR: backfill-dispatch-rows: --only-mode requires --for-date "
            "(without it every row is skipped and this command would exit 0 "
            "having dispatched nothing)",
            file=sys.stderr,
        )
        return 1

    for date, base, tip in rows:
        if args.only_mode and date != args.for_date:
            continue

        if date in processed_dates:
            print(
                f"WARN: backfill-dispatch-rows: duplicate row for {date} in "
                "gap-rows input -- skipping (already dispatched)",
                file=sys.stderr,
            )
            continue

        processed_dates.add(date)
        span_flag = f"{base}..{tip}" if base and tip else None
        scope_arg = (
            args.scope_summary
            if (date == args.for_date and args.scope_summary)
            else None
        )

        rc = _dispatch_step9_row(date, span_flag, scope_arg, args.no_push, args.dry_run)
        if rc != 0:
            print(
                f"ERROR: backfill-dispatch-rows: step9-dispatch failed for {date} "
                f"(rc={rc})",
                file=sys.stderr,
            )
            overall_rc = 1

    if args.for_date and args.for_date not in processed_dates:
        print(
            f"INFO: --for-date {args.for_date} not detected as a gap (already "
            "wrapped, no commits, or beyond 14-day lookback); nothing to do."
        )

    return overall_rc


def main(argv: list[str] | None = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    try:
        require_colocated_engine_on_path(__file__)
    except RuntimeError as _exc:
        print(f"{Path(__file__).name}: engine-root resolution failed: {_exc}", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        prog="workday-complete-close",
        description="Late-ceremony orchestration logic for /workday-complete "
        "(Step 4d / Step 9 dispatch / Step 10.5 / Step 10.6).",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_stitch = sub.add_parser("stitch-sidecar", help="Step 4d: stitch the observer sidecar.")
    p_stitch.add_argument("--today", default=None, help="Override TODAY (default: local calendar day).")
    p_stitch.set_defaults(func=cmd_stitch_sidecar)

    p_step9 = sub.add_parser("step9-dispatch", help="Step 9: changelog-append dispatch gate.")
    p_step9.add_argument("scope_summary", nargs="?", default=None)
    p_step9.add_argument("--only-mode", action="store_true")
    p_step9.add_argument("--no-push", action="store_true")
    p_step9.add_argument("--dry-run", action="store_true")
    p_step9.add_argument("--commit-span", default=None)
    p_step9.add_argument("--for-date", default=None)
    p_step9.set_defaults(func=cmd_step9_dispatch)

    p_hook = sub.add_parser("ceremony-hook", help="Step 10.5: post-ceremony command hook.")
    p_hook.add_argument("--only-mode", action="store_true")
    p_hook.set_defaults(func=cmd_ceremony_hook)


    p_backfill = sub.add_parser(
        "backfill-dispatch-rows",
        help="Step 3.5 Phase B: dispatch step9 across gap rows read from stdin.",
    )
    p_backfill.add_argument("--for-date", default=None)
    p_backfill.add_argument("--allow-empty", action="store_true")
    p_backfill.add_argument("--only-mode", action="store_true")
    p_backfill.add_argument("--scope-summary", default=None)
    p_backfill.add_argument("--no-push", action="store_true")
    p_backfill.add_argument("--dry-run", action="store_true")
    p_backfill.set_defaults(func=cmd_backfill_dispatch_rows)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
