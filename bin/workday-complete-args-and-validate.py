"""workday-complete-args-and-validate.py — /workday-complete front-door arg
parsing + cross-machine targeted-wrap guard + Step-1 validate invocation.

Ports three residual bash logic blocks out of commands/workday-complete.md
into one naked-Python CLI (M3 extirpation wave, chunk WDC-1):

  1. `parse-front-door <arguments>` — extracts `--for-date <YYYY-MM-DD>` and
     `--only` out of the raw $ARGUMENTS string before any ceremony step
     executes (§ Argument Parsing (Front Door)). Without this front door,
     these flags would be forwarded verbatim to Step 9 as scope-summary
     prose (silently inert but noise-inducing). Fails loud (exit 1) when
     `--only` appears without `--for-date` — a targeted wrap needs a target
     date; without this guard the ceremony would silently run a near-no-op.

  2. `check-cross-machine <arguments>` — `--for-date` is restricted to the
     current machine. Passing `--machine <other>` alongside `--for-date` is
     not supported: the Phase B machinery does not call Step 9 for a
     non-current machine, so a cross-machine `--for-date` would silently
     produce a summary-only block (footgun). This fails loud instead
     (§ Argument Parsing (Front Door), "Cross-machine restriction").

  3. `run-step1 [extra-args...]` — invokes the co-located
     workday-complete-step1-validate.py and re-emits its eval-safe
     `RC_UBT=... RC_VALIDATE=...` stdout line verbatim, propagating its exit
     code as this CLI's own exit code. Ports the bash "capture stdout and rc
     SEPARATELY, then eval" dance (§ Step 1: Validate) — `eval "$(script)"`
     discards the script's real exit code (command substitution swallows
     it), so the bash original had to capture stdout first, stash `$?`, THEN
     eval the assignment line. `subprocess.run()` gives both natively in one
     call — no eval trick needed in Python — so this subcommand exists
     purely so callers invoke one name instead of re-deriving the
     separate-capture dance inline at every call site.

Each subcommand is independently self-contained (no dependency on another
subcommand having run first in the same process) and self-resolving
(`Path(__file__)`-relative; no cwd dependence) — safe to invoke as three
separate subprocess calls from the DoE ceremony fence.

Spec backlink: commands/workday-complete.md § Argument Parsing (Front Door),
§ Step 1: Validate (DoE-claude repo, C6 —
docs/plans/2026-07-07-workday-complete-local-day-and-targeted-wrap.md).

Stdout contracts (eval-safe; values `shlex.quote`'d — eval-injection defence,
one step stronger than workday-complete-step1-validate.py's plain
single-quoting, since scope-summary is free-form user prose that may itself
contain a single quote):
  parse-front-door:    one line, `FOR_DATE=<q> ONLY_MODE=<0|1> ONLY_FLAG=<q> SCOPE_SUMMARY=<q>`
                       ONLY_FLAG is the ready-to-interpolate CLI form of ONLY_MODE:
                       `--only` when set, empty string otherwise. It exists so a
                       caller can splice `$ONLY_FLAG` straight into an argv without
                       a shell value-test — `${ONLY_MODE:+--only}` is a trap, since
                       ONLY_MODE is `0`/`1` and `0` is a non-empty string, so that
                       expansion emits `--only` on the off case too.
  check-cross-machine: no stdout on pass/not-applicable; ERROR to stderr + exit 1 on mismatch
  run-step1:           forwards workday-complete-step1-validate.py's own stdout line verbatim

Exit codes:
  parse-front-door:    0 ok; 1 `--only` without `--for-date`.
  check-cross-machine: 0 ok or not-applicable (no `--for-date`, or no `--machine`); 1 mismatch.
  run-step1:           forwards workday-complete-step1-validate.py's exit code verbatim.
"""
from __future__ import annotations

import os
import re
import shlex
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

_FOR_DATE_RE = re.compile(r"--for-date\s+(\d{4}-\d{2}-\d{2})\s*")
_ONLY_RE = re.compile(r"--only\s*")
_MACHINE_RE = re.compile(r"--machine\s+(\S+)")


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def cmd_parse_front_door(arguments: str) -> int:
    args_tmp = arguments

    for_date = ""
    m = _FOR_DATE_RE.search(args_tmp)
    if m:
        for_date = m.group(1)
        args_tmp = _FOR_DATE_RE.sub("", args_tmp, count=1)

    only_mode = 0
    if _ONLY_RE.search(args_tmp):
        only_mode = 1
        args_tmp = _ONLY_RE.sub("", args_tmp, count=1)

    scope_summary = args_tmp.strip()

    if only_mode == 1 and not for_date:
        _err(
            "ERROR: --only requires --for-date <YYYY-MM-DD>; a targeted wrap "
            "needs a target date."
        )
        return 1

    print(
        f"FOR_DATE={shlex.quote(for_date)} ONLY_MODE={only_mode} "
        f"ONLY_FLAG={shlex.quote('--only' if only_mode else '')} "
        f"SCOPE_SUMMARY={shlex.quote(scope_summary)}"
    )
    return 0


def _current_machine() -> str:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke
    cc_invoke.require_engine_on_path(__file__)
    from coordinator_core.machine_resolver import compute_machine

    return compute_machine()


def cmd_check_cross_machine(arguments: str) -> int:
    if not _FOR_DATE_RE.search(arguments):
        return 0

    m = _MACHINE_RE.search(arguments)
    if not m:
        return 0

    arg_machine = m.group(1)

    try:
        cur_machine = _current_machine()
    except (RuntimeError, ImportError) as exc:
        _err(f"ERROR: cannot resolve current machine for cross-machine check: {exc}")
        return 1

    if arg_machine != cur_machine:
        _err(
            f"ERROR: cross-machine targeted wrap is not supported; run "
            f"`/workday-complete` on `{arg_machine}` directly"
        )
        return 1

    return 0


def cmd_run_step1(extra: list[str]) -> int:
    step1_path = os.path.join(_BIN_DIR, "workday-complete-step1-validate.py")
    if not os.path.isfile(step1_path):
        _err(
            f"ERROR: {step1_path} not found — stale or partial claude-klabauter "
            "checkout."
        )
        return 1

    del extra

    import contextlib
    import importlib.util
    import io

    spec = importlib.util.spec_from_file_location("workday_complete_step1_validate", step1_path)
    step1_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(step1_module)

    stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf):
        rc = step1_module.main()

    stdout_text = stdout_buf.getvalue()
    if stdout_text:
        sys.stdout.write(stdout_text)
        if not stdout_text.endswith("\n"):
            sys.stdout.write("\n")
    return rc


_USAGE = (
    "usage: workday-complete-args-and-validate.py <subcommand> <args...>\n"
    "subcommands:\n"
    "  parse-front-door <arguments>     extract --for-date/--only from $ARGUMENTS\n"
    "  check-cross-machine <arguments>  fail loud on --for-date + --machine <other>\n"
    "  run-step1 [extra-args...]        invoke workday-complete-step1-validate.py\n"
)

_HELP_FLAGS = ("--help", "-h", "help")


def main(argv: list[str]) -> int:
    if not argv:
        _err(_USAGE)
        return 2
    subcmd, rest = argv[0], argv[1:]

    if subcmd in _HELP_FLAGS:
        print(_USAGE)
        return 0

    if subcmd == "parse-front-door":
        if not rest:
            _err("usage: workday-complete-args-and-validate.py parse-front-door <arguments>")
            return 2
        return cmd_parse_front_door(rest[0])

    if subcmd == "check-cross-machine":
        if not rest:
            _err("usage: workday-complete-args-and-validate.py check-cross-machine <arguments>")
            return 2
        return cmd_check_cross_machine(rest[0])

    if subcmd == "run-step1":
        return cmd_run_step1(rest)

    _err(f"workday-complete-args-and-validate.py: unknown subcommand {subcmd!r}\n{_USAGE}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
