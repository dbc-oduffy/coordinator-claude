#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""validate-fast-and-packageability.py -- naked-Python port of the two bash
fences embedded in DoE-claude's coordinator/skills/validate/SKILL.md ("How to
Run" and "Packageability-contract check").

Purpose: single self-contained CLI exposing the two independently-reported
checks the /validate skill runs at cadence gates -- resolve + execute the
per-repo fast-test command (`fast` subcommand), and run the opt-in
packageability-manifest contract check (`packageability` subcommand). Both
subcommands are self-resolving (Path(__file__)-relative) and idempotent --
no cwd dependence beyond the repo root each check is scoped to run against
(the caller's cwd, exactly as the ported bash fences ran against the
invoking shell's cwd).

Why this exists as one file, not two: the DoE ceremony step (/validate)
always runs both checks back-to-back and reports them as two independent
lines (`Validation: <x>` / `Packageability: <y>`) -- a single CLI with two
subcommands mirrors that pairing without forcing two separate bin/ entries
for what is one ceremony step's logic.

Subcommands:
  validate-fast-and-packageability.py fast [--repo-root PATH]
      Resolves the fast-test command via coordinator-resolve-validation-cmd
      (co-located in coordinator/bin, loaded in-process by file path -- no
      subprocess hop for the resolution step itself), maps its exit-code
      contract onto the
      `Validation:` enum documented in SKILL.md's "Exit Code -> Validation:
      Mapping" table, executes the resolved command as a direct argv vector
      (`shlex.split`, no shell) when one resolved, and prints exactly one
      `Validation: <value>` line to stdout.
      Exit code: the numeric `Validation:` value when the resolved command
      ran (0 on pass, its own exit code on failure); 0 for `skipped`; 1 for
      `config-malformed` / `interp-missing` / `shell-metachar` (the last is a
      configured value containing shell syntax `shlex.split` cannot express --
      pipe/chain/redirect/substitution -- see _fail_on_ambiguous_shell_syntax;
      all three documented as blocking in SKILL.md, unlike skipped); 3 for
      `tier-u-refused` (the resolved
      command classifies Tier U -- unscoped/full-suite shape -- and the
      calling session holds no live Tier-U grant; R3+R4,
      cross-repo/inbox/2026-07-25-doe-claude-em-validate-tier-u-shape-
      ruling.md). This is an ADDED contract beyond the ported bash fence
      (which never itself exited non-zero -- callers parsed the printed
      line) -- see the "Divergence from the bash fence" note below.

  validate-fast-and-packageability.py packageability [-- <passthrough-args>]
      Runs the co-located validate-install-contract.py (same coordinator/bin
      directory -- no cross-repo resolution needed, since both CLIs live in
      claude-klabauter now) against the invoking repo's own manifest, with a
      loud-skip guard (WARN to stderr, PACKAGEABILITY_EXIT=0) when that
      script is absent from an otherwise-valid bin/ dir (partial/stale
      checkout). Any args after `--` (or, for ergonomics, any trailing args
      at all) are forwarded verbatim to validate-install-contract.py (e.g.
      --manifest-path). Prints exactly one `Packageability: <exit-code>`
      line to stdout. Exit code: the packageability check's own exit code
      (0 on compliant/not-opted-in/skip, its own non-zero on findings).

Divergence from the bash fence: the original bash fence never itself
`exit`ed with the classified result -- it only echoed the `Validation:` /
`Packageability:` line and let the caller parse stdout. This CLI additionally
exits with a code matching that line, so a caller CAN use the CLI's own exit
status directly (`if fast-and-packageability fast; then ...`) without a
stdout-parsing step, while remaining fully backward-compatible with a caller
that only greps the printed line (as the current /validate SKILL.md fence
does). This is a deliberate, noted improvement -- not a silent behavior
change to the printed contract.

Port source: coordinator/skills/validate/SKILL.md (DoE-claude) -- "How to
Run" fence (mktemp diagnostic capture + rc==2/126/other-nonzero/0 ladder)
and "Packageability-contract check" fence (validate-install-contract.py
loud-skip-vs-silent-pass guard). The resolve-claude-klabauter-bin resolver block, the
_cc_trusted/_cc_root guard preamble, and the thin single-CLI-invocation
shape of `python3 "${_mkb_bin}/validate-install-contract.py"` are NOT ported
here -- those are the D1/D2 repoint's concern (the DoE-side caller resolves
this CLI's own location the same way it resolved the two bash fences'
targets, then invokes this CLI by name).

Spec backlink: docs/plans/2026-07-19-debash-coordinator-windows.md (M3
chunk C-VALIDATE)

Negative-spec:
  - Does NOT fold Packageability's exit code into Validation's -- they are
    independently reported, exactly as SKILL.md documents ("VALIDATION_RESULT
    is untouched by this check").
  - Does NOT pre-parse, probe, or validate the resolved fast-test command's
    FIRST TOKEN before execution -- matches coordinator-resolve-validation-cmd's
    own no-first-token-heuristic contract (the Staff Engineer F5). This is narrower than
    "no validation at all": _fail_on_ambiguous_shell_syntax DOES refuse a
    value containing shell metacharacters (pipe/chain/redirect/substitution)
    before running it, because direct exec (no shell, as of the 2026-07-29
    debash pass) cannot honor that syntax -- silently mis-running it would be
    the same quiet-corruption shape the Staff Engineer F5 exists to avoid, not a
    contradiction of it. The refusal is about the SHAPE of the whole string,
    never about probing whether the first token names a real executable.
  - Does NOT wire the packageability check into any cross-repo/fleet-shared
    hook -- it is invoked only against the calling repo's own manifest, at
    that repo's own request (docs/wiki/agent-install-contract.md §
    Packageability).
  - The `fast` subcommand NEVER calls ``write_tier_u_grant`` -- R4
    (cross-repo/inbox/2026-07-25-doe-claude-em-validate-tier-u-shape-
    ruling.md) requires /validate to gate on shape and REFUSE, never to
    write or consume-by-granting a Tier-U grant. It only READS one via
    ``coordinator_core.session.tier_u_gate.enforce_tier_u_gate``.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import os
import re
import shlex
import subprocess
import sys

_BIN_DIR = os.path.dirname(os.path.abspath(__file__))

# coordinator_core is co-located in this same repo (claude-klabauter) -- resolve
# the repo root via the same cc_invoke helper the sibling CLIs use and put it
# on sys.path, so `coordinator_core.session.tier_u_gate` (R3+R4 shape gate)
# imports cleanly regardless of the caller's own cwd/sys.path.
_LIB_DIR = os.path.join(_BIN_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import resolve_colocated_claude_klabauter_root, child_env  # noqa: E402

try:
    _REPO_ROOT = resolve_colocated_claude_klabauter_root(__file__)
except RuntimeError as _exc:
    print(f"{os.path.basename(__file__)}: CLAUDE_KLABAUTER_ROOT resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from coordinator_core.diff_scoped_tests import (  # noqa: E402
    PYTEST_NO_TESTS_COLLECTED,
    append_test_paths,
    find_changed_test_files,
)

# Aliased deliberately: ``run_fast`` binds a LOCAL ``diag`` to the resolver's
# captured stderr string (``diag = diag_buf.getvalue()``), which would shadow
# a bare ``diag`` import for the whole function and make every call site a
# ``TypeError: 'str' object is not callable``.
from coordinator_core.diff_scoped_tests import diag as diff_diag  # noqa: E402
from coordinator_core.session.tier_u_gate import enforce_tier_u_gate  # noqa: E402

# coordinator-resolve-validation-cmd.py is co-located in this same bin/ dir.
# Its on-disk filename is hyphenated (a bin/-resident CLI, not an importable
# package member) -- a hyphen is not a valid Python identifier character, so
# a bareword `import` can never resolve it regardless of sys.path. Load by
# explicit file path instead.
_RVC_PATH = os.path.join(_BIN_DIR, "coordinator-resolve-validation-cmd.py")
_rvc_spec = importlib.util.spec_from_file_location("coordinator_resolve_validation_cmd", _RVC_PATH)
_resolver = importlib.util.module_from_spec(_rvc_spec)
sys.modules[_rvc_spec.name] = _resolver
_rvc_spec.loader.exec_module(_resolver)  # noqa: E402

_VALIDATE_INSTALL_CONTRACT = os.path.join(_BIN_DIR, "validate-install-contract.py")


# --------------------------------------------------------------------------
# fast subcommand
# --------------------------------------------------------------------------

# Any one of these implies real shell semantics (pipe, chain, redirect,
# command substitution) that a direct-exec argv vector cannot express -- a
# single `|`, `&`, `;`, `<`, `>`, backtick, or `$(` already tells the story
# (`&&`/`||` contain `&`/`|` and so match too; no need to spell them out).
_SHELL_METACHAR_RE = re.compile(r"[|&;<>`]|\$\(")


class AmbiguousShellSyntax(Exception):
    """Raised when a configured fast-test command carries shell metacharacters
    this direct-exec caller cannot honor (see _fail_on_ambiguous_shell_syntax)."""


def _fail_on_ambiguous_shell_syntax(cmd: str) -> None:
    """Fail loud when `cmd` carries shell syntax `shlex.split` cannot express.

    The resolved fast-test command used to run via `bash -c`, which happily
    gave pipe/chain/redirect/substitution syntax real shell meaning. It now
    runs as a direct argv vector (no shell interposed) via `shlex.split`, so
    that same syntax would silently degrade into a literal token handed to
    the resolved program -- `pytest -m x && pytest -m y` would invoke pytest
    with a literal `&&` argument instead of chaining two runs, exactly the
    quiet-corruption-wearing-a-costume shape that motivated
    coordinator-resolve-validation-cmd.py's own exit-126 escaped-quote guard.
    Matches that module's fail-loud-on-ambiguous-value posture rather than
    inventing a second convention. Raises AmbiguousShellSyntax; run_fast maps
    it to `Validation: shell-metachar` / exit 1 (a CONFIG defect, not a
    test/build failure).
    """
    m = _SHELL_METACHAR_RE.search(cmd)
    if not m:
        return
    print(
        f"FAIL: configured fast-test command contains a shell metacharacter "
        f"({m.group()!r}) implying pipe/chain/redirect/substitution semantics -- "
        "this command now runs directly (no shell) via shlex.split, so that "
        f"syntax would silently become a literal argv token: {cmd}",
        file=sys.stderr,
    )
    print(
        "Express it as a plain argument vector -- for a genuine pipeline or "
        "chain, wrap it in a script and configure that script's path.",
        file=sys.stderr,
    )
    raise AmbiguousShellSyntax(cmd)


def _run_resolved_command(cmd: str) -> int:
    """Execute the resolved fast-test command as a direct argv vector
    (`shlex.split`, no shell) -- the metacharacter guard already refused any
    value shlex.split cannot faithfully express, so parsing here matches the
    shell-quoting the value is written with, minus the shell itself.

    Deliberate isolation boundary -- do not convert to an in-process
    import. This is pytest process isolation: the resolved validation
    command must run as its own process, not be imported and called
    in-line. Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    argv = shlex.split(cmd)
    # env=child_env(): strip COORDINATOR_CORE_LAZY_OPS before spawning -- this repo's
    # own pytest suite asserts the op-registry at collection time, and a leaked
    # COORDINATOR_CORE_LAZY_OPS=1 (from importing cc_invoke above) makes
    # coordinator_core.ops skip eager registration, breaking collection on a green
    # tree (see commit 5943ec01, which patched the sibling workday-complete-step1-
    # validate.py copy of this exact leak by hand before child_env() existed).
    try:
        proc = subprocess.run(
            argv,
            env=child_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.returncode
    except OSError as exc:
        # `bash -c` used to report an unresolvable first token as rc=127;
        # direct exec instead raises (FileNotFoundError on both POSIX and
        # Windows for CreateProcess ERROR_FILE_NOT_FOUND). Preserve the rc=127
        # contract rather than letting this escape as an uncaught traceback.
        print(f"command not found: {argv[0]!r} ({exc})", file=sys.stderr)
        return 127


def run_fast(repo_root: str | None) -> tuple[str, int]:
    """Resolve + (when resolved) execute the fast-test command.

    Returns (validation_result, cli_exit_code) -- validation_result is the
    string printed after `Validation: ` per SKILL.md's Exit Code -> Validation:
    Mapping table; cli_exit_code is this CLI's own process exit code (see
    module docstring's "Divergence from the bash fence" note).

    Diagnostic stderr from the resolver is captured (mirrors the bash
    fence's mktemp-file capture) and only re-emitted on the non-success
    branches (skip / config-malformed / interp-missing) -- the success
    branch stays silent on the resolver's own diagnostic, exactly as the
    bash fence's `[[ $RESOLVER_EXIT -eq 2 ]]`-gated `cat "$_DIAG_TMP"`
    calls did (never invoked on the RESOLVER_EXIT -eq 0 path).
    """
    diag_buf = io.StringIO()
    with contextlib.redirect_stderr(diag_buf):
        result = _resolver.resolve_fast_test_cmd(repo_root)
    diag = diag_buf.getvalue()

    if result.returncode == 2:
        # skip-with-notice
        if diag:
            print(diag, end="", file=sys.stderr)
        return "skipped", 0

    if result.returncode == 126:
        # Malformed configured value -- a CONFIG defect, not a test/build
        # failure. Blocking (SKILL.md's mapping table).
        if diag:
            print(diag, end="", file=sys.stderr)
        return "config-malformed", 1

    if result.returncode != 0:
        # Any OTHER resolver non-zero (canonical: 127, bare `python` token
        # with no python3/python on PATH) is a HARD environment failure,
        # NOT a skip. Blocking.
        if diag:
            print(diag, end="", file=sys.stderr)
        return "interp-missing", 1

    cmd = result.stdout.rstrip("\n")

    # Shell-metachar guard runs on the CONFIGURED command, before any
    # diff-scoping -- it is a config-validity check (can this value even be
    # run without a shell?), independent of which test paths this run gets
    # scoped to.
    try:
        _fail_on_ambiguous_shell_syntax(cmd)
    except AmbiguousShellSyntax:
        return "shell-metachar", 1

    # Diff-scoping: when the working tree has changed test files, append
    # them onto the resolved command so this gate runs only those files
    # instead of the whole configured fast tier. Empty changed-test-file
    # set -> behaviour unchanged (scoped_cmd == cmd). See
    # coordinator_core/diff_scoped_tests.py for the "changed test file"
    # definition and the append-only (never rebuild) contract that keeps
    # the `-m '...'` marker selector intact.
    diff_paths = find_changed_test_files(repo_root)
    if diff_paths:
        scoped_cmd = append_test_paths(cmd, diff_paths)
        diff_diag(f"changed test file(s) detected -- scoping run to: {', '.join(diff_paths)}")
    else:
        scoped_cmd = cmd

    # Resolver succeeded -- classify the resolved command's SHAPE before
    # running it (R3+R4: this is the process-boundary seam the ruling memo
    # asked to be closed -- the resolved command never appears as
    # PreToolUse(Bash) text, so Layer 3 alone would never see it). Refuse
    # rather than execute when the shape is Tier U and the calling session
    # holds no live Tier-U grant; this CLI only READS a grant, never writes
    # one (enforce_tier_u_gate's own negative-spec). Gated on scoped_cmd --
    # the command actually about to execute -- not the unscoped cmd.
    gate = enforce_tier_u_gate(scoped_cmd, repo_root=repo_root)
    if not gate.proceed:
        print(gate.refusal_message, file=sys.stderr)
        return "tier-u-refused", 3

    cmd_exit = _run_resolved_command(scoped_cmd)

    if diff_paths and cmd_exit == PYTEST_NO_TESTS_COLLECTED:
        # The diff-scoped run named a changed test file the `-m` marker
        # filter then deselected entirely (e.g. it carries only
        # designed_red-marked tests) -- pytest's own "no tests collected"
        # exit code. That is neither a pass nor a failure; fall back to
        # the full configured fast tier so the gate still runs SOMETHING
        # (fail-safe: always toward more testing, never toward silently
        # running zero tests).
        diff_diag(
            "diff-scoped run collected zero tests (pytest rc="
            f"{PYTEST_NO_TESTS_COLLECTED}) -- falling back to the full "
            "configured fast tier."
        )
        gate_full = enforce_tier_u_gate(cmd, repo_root=repo_root)
        if not gate_full.proceed:
            print(gate_full.refusal_message, file=sys.stderr)
            return "tier-u-refused", 3
        cmd_exit = _run_resolved_command(cmd)

    return str(cmd_exit), cmd_exit


def _cmd_fast(args: argparse.Namespace) -> int:
    validation_result, exit_code = run_fast(args.repo_root)
    print(f"Validation: {validation_result}")
    return exit_code


# --------------------------------------------------------------------------
# packageability subcommand
# --------------------------------------------------------------------------


def run_packageability(passthrough: list[str]) -> tuple[int, str | None]:
    """Run the co-located validate-install-contract.py, or loud-skip when
    absent. Returns (packageability_exit, warn_message_or_none).

    Deliberate isolation boundary -- do not convert to an in-process
    import. This is a distinct interpreter plus clean import state:
    packageability is only meaningful in a fresh interpreter, so
    validate-install-contract.py must run as its own process. Reason
    recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    if not os.path.isfile(_VALIDATE_INSTALL_CONTRACT):
        # coordinator/bin itself is where THIS script lives -- this guard is
        # ONLY about validate-install-contract.py specifically being absent
        # (a partial/older checkout). Loud SKIP, never a silent
        # PACKAGEABILITY_EXIT=0-and-say-nothing.
        warn = (
            "WARN: Packageability check SKIPPED -- "
            f"'{_VALIDATE_INSTALL_CONTRACT}' not found; this coordinator/bin "
            "checkout has no validate-install-contract.py (partial/stale "
            "checkout) -- the invoking repo's own opt-in manifest check was "
            "not run"
        )
        print(warn, file=sys.stderr)
        return 0, warn

    python_bin = sys.executable or "python3"
    proc = subprocess.run(
        [python_bin, _VALIDATE_INSTALL_CONTRACT, *passthrough],
        env=child_env(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return proc.returncode, None


def _cmd_packageability(args: argparse.Namespace) -> int:
    packageability_exit, _warn = run_packageability(args.passthrough)
    print(f"Packageability: {packageability_exit}")
    return packageability_exit


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate-fast-and-packageability",
        description=(
            "Resolve+run the fast-test command, and/or run the opt-in "
            "packageability-manifest contract check."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    fast_p = sub.add_parser("fast", help="resolve and run the fast-test command")
    fast_p.add_argument(
        "--repo-root",
        default=None,
        help="repo root to resolve against (default: cwd)",
    )
    fast_p.set_defaults(func=_cmd_fast)

    pkg_p = sub.add_parser(
        "packageability", help="run the packageability-manifest contract check"
    )
    pkg_p.add_argument(
        "passthrough",
        nargs=argparse.REMAINDER,
        help="args forwarded verbatim to validate-install-contract.py (e.g. --manifest-path PATH)",
    )
    pkg_p.set_defaults(func=_cmd_packageability)

    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    # argparse.REMAINDER can leave a leading "--" separator -- strip it so
    # `packageability -- --manifest-path X` and `packageability --manifest-path X`
    # forward identically.
    if getattr(args, "passthrough", None) and args.passthrough[0] == "--":
        args.passthrough = args.passthrough[1:]
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
