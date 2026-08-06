#!/usr/bin/env python3
"""workday-complete-step1-validate.py — /workday-complete Step 1 gate (fast-test).

Encapsulates the fast-test blocking gate from commands/workday-complete.md
§Step 1 (all repos, skipped when unconfigured).

Exists so the EM cannot accidentally skip this gate when running the
workday-complete ceremony inline.

UBT (Unreal Build Tool) pending-record resolution gate RETIRED 2026-08-06
(shell-spawn-regrowth-gate C7b): this gate was presence-detected on
`bin/check-ubt-build-fresh.sh` relative to cwd and, when present, invoked it
via `["bash", ubt_path, ...]` -- an unconditional bash-binary spawn the
2026-08-06 no-shell-spawns ruling does not tolerate. Evidence the gate fired
nowhere: no repo in the local sibling-repo checkout root ships
`bin/check-ubt-build-fresh.sh` (exhaustive `find -iname` across the checkout
root found zero matches). The one candidate consuming repo,
Example-game-workbench-repo, already retired its own copy of this exact script in
its de-bash campaign (commit 290eaa298, "retire the coupled install core —
tracked bash 38 -> 1") and reimplements the equivalent check as
`bin/check_ubt_build_fresh.py` (Python, underscore-named -- a path this
gate's hyphenated presence-detection could never have matched even before
the retirement). A presence-detected gate with no live producer anywhere in
reach is dead weight; deleting it needs no allowlist carve-out. RC_UBT is
now hardcoded "skipped" for wire-format stability with existing callers.

Spec backlink: commands/workday-complete.md §Step 1

Stdout (caller eval's this line):
  RC_UBT='skipped' RC_VALIDATE='<n|skipped|lib-missing|interp-missing|config-malformed|shell-metachar|tier-u-refused>'
  Exactly one line, shell-eval-safe (values single-quoted — eval injection defence).
  RC_UBT is now always 'skipped' (Gate 1 retired above); the field is kept
  for wire-format stability with existing callers rather than removed.

Stderr: all human-readable detail (fast-test output, resolver hints).

Exit codes:
  0 — fast-test gate ok or skipped; proceed.
  2 — fast-test build failure (patterns error:/BUILD FAILED/Compilation), OR exit 127
       (missing interpreter/binary), OR resolver failed with interp-missing, OR the
       configured fast_test_cmd was malformed (resolver exit 126 -> config-malformed),
       OR the configured fast_test_cmd carries a shell metacharacter implying real
       shell semantics that this direct-exec caller cannot honor (RC_VALIDATE=
       shell-metachar — see _fail_on_ambiguous_shell_syntax below).
  3 — fast-test test-only failure (fix-quick or flag).
  4 — resolver lib missing at resolved path (fast-test skipped; RC_VALIDATE=lib-missing).
  5 — resolved fast-test command classifies Tier U (unscoped/full-suite shape) and the
       calling session holds no live Tier-U grant (RC_VALIDATE=tier-u-refused). R3+R4,
       cross-repo/inbox/2026-07-25-doe-claude-em-validate-tier-u-shape-ruling.md — this
       gate only READS a Tier-U grant, it never writes/consumes-by-granting one.

Port of: workday-complete-step1-validate.sh (DoE 091c0f3e, 2026-07-19).
The fast-test resolver (bin/coordinator-resolve-validation-cmd.py, ported from
lib/coordinator-resolve-validation-cmd.sh, DoE c187f5b9, 2026-07-21, in the
2026-07-19 debash campaign's E3-e chunk) is now called in-process — no bash-lib
bridge subprocess spawn. The resolved fast_test_cmd itself is executed via
`shlex.split` + direct exec (no shell) as of the 2026-07-29 debash pass —
see _fail_on_ambiguous_shell_syntax for the guard this removal requires.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shlex
import subprocess
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The resolver's on-disk filename is hyphenated (bin/-resident CLI, not an
# importable package member) — a hyphen is not a valid Python identifier
# character, so a bareword `import` can never resolve it regardless of
# sys.path. Load by explicit file path instead.
_RVC_PATH = os.path.join(PLUGIN_ROOT, "bin", "coordinator-resolve-validation-cmd.py")
_rvc_spec = importlib.util.spec_from_file_location("coordinator_resolve_validation_cmd", _RVC_PATH)
rvc = importlib.util.module_from_spec(_rvc_spec)
sys.modules[_rvc_spec.name] = rvc
_rvc_spec.loader.exec_module(rvc)  # noqa: E402

# coordinator_core is co-located in this same repo (claude-klabauter) -- resolve
# the repo root via the shared cc_invoke helper and put it on sys.path, so
# `coordinator_core.session.tier_u_gate` (R3+R4 shape gate) imports cleanly
# regardless of the caller's own cwd/sys.path.
_LIB_DIR = os.path.join(PLUGIN_ROOT, "bin", "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import resolve_colocated_claude_klabauter_root  # noqa: E402

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
    diag,
    find_changed_test_files,
)
from coordinator_core.session.tier_u_gate import enforce_tier_u_gate  # noqa: E402

# "error:" is compiler-diagnostic-shaped (gcc/clang/tsc: "path/file.c:12:5: error:
# ...") only when NOT immediately preceded by a letter — a Python exception name
# lowercases to e.g. "assertionerror:" / "jsondecodeerror:", always with a
# letter directly before "error:". The negative lookbehind excludes those while
# still matching the compiler shape (preceded by ": ", whitespace, or nothing).
_BUILD_RE = re.compile(r"(?<![a-z])error:|build failed|compilation")

# Any one of these implies real shell semantics (pipe, chain, redirect,
# command substitution) that a direct-exec argv vector cannot express — a
# single `|`, `&`, `;`, `<`, `>`, backtick, or `$(` already tells the story
# (`&&`/`||` contain `&`/`|` and so match too; no need to spell them out).
_SHELL_METACHAR_RE = re.compile(r"[|&;<>`]|\$\(")


class AmbiguousShellSyntax(Exception):
    """Raised when a configured fast_test_cmd carries shell metacharacters this
    direct-exec caller cannot honor (see _fail_on_ambiguous_shell_syntax)."""


def _fail_on_ambiguous_shell_syntax(cmd: str) -> None:
    """Fail loud when `cmd` carries shell syntax `shlex.split` cannot express.

    The resolved fast_test_cmd used to run via `bash -c`, which happily gave
    pipe/chain/redirect/substitution syntax real shell meaning. It now runs as
    a direct argv vector (no shell interposed) via `shlex.split`, so that same
    syntax would silently degrade into a literal token handed to the resolved
    program — `pytest -m x && pytest -m y` would invoke pytest with a literal
    `&&` argument instead of chaining two runs, exactly the kind of
    quiet-corruption-wearing-a-costume that motivated
    coordinator-resolve-validation-cmd.py's own exit-126 escaped-quote guard.
    Matches that module's fail-loud-on-ambiguous-value posture rather than
    inventing a second convention. Raises AmbiguousShellSyntax; callers map it
    to RC_VALIDATE=shell-metachar / exit 2 (a CONFIG defect, not a test/build
    failure).
    """
    m = _SHELL_METACHAR_RE.search(cmd)
    if not m:
        return
    print(
        f"[workday-complete-step1] fast-test: configured command contains a shell "
        f"metacharacter ({m.group()!r}) implying pipe/chain/redirect/substitution "
        "semantics — this command now runs directly (no shell) via shlex.split, so "
        f"that syntax would silently become a literal argv token: {cmd}",
        file=sys.stderr,
    )
    print(
        "[workday-complete-step1] Express it as a plain argument vector — for a "
        "genuine pipeline or chain, wrap it in a script and configure that script's path.",
        file=sys.stderr,
    )
    raise AmbiguousShellSyntax(cmd)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _emit(rc_ubt, rc_validate) -> None:
    """Emit the single eval-safe stdout line (single-quoted values)."""
    print(f"RC_UBT='{rc_ubt}' RC_VALIDATE='{rc_validate}'")


def _run_fast_test_cmd(cmd: str, env: dict) -> tuple[int, str]:
    """Run the resolved fast-test command as a direct argv vector (no shell)
    via `shlex.split` — the metacharacter guard (`_fail_on_ambiguous_shell_
    syntax`) already refused any value shlex.split cannot faithfully
    express, so parsing here matches the shell-quoting the value is written
    with, minus the shell itself. Forwards combined stdout+stderr to this
    process's stderr live, and returns (returncode, combined_content) for
    classification. Shared by the initial (possibly diff-scoped) attempt and
    the rc=5 full-tier / no-tests-collected fallback, so both runs forward
    output and classify identically.

    Deliberate isolation boundary -- do not convert to an in-process
    import. This is pytest process isolation: the project's fast-test
    command must run as its own process, not be imported and called
    in-line. Reason recorded in
    state/audits/2026-08-06-self-spawn-isolation-boundary-classification.md.
    """
    _err(f"[workday-complete-step1] fast-test: running: {cmd}")
    argv = shlex.split(cmd)
    try:
        ft = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        ft_content = (ft.stdout or "") + (ft.stderr or "")
        ft_rc = ft.returncode
    except OSError as exc:
        # `bash -c` used to report an unresolvable first token as rc=127 with
        # "command not found" on stdout/stderr; direct exec instead raises
        # (FileNotFoundError on both POSIX and Windows for CreateProcess
        # ERROR_FILE_NOT_FOUND). Preserve the rc=127 contract
        # _classify_fast_test_output already keys off of, rather than letting
        # this escape as an uncaught traceback.
        ft_content = f"[workday-complete-step1] fast-test: command not found: {argv[0]!r} ({exc})\n"
        ft_rc = 127
    if ft_content:
        sys.stderr.write(ft_content)
        sys.stderr.flush()
    return ft_rc, ft_content


def _classify_fast_test_output(output: str, rc: int) -> int:
    """Return 2 (build failure) or 3 (test-only failure) for a non-zero fast-test rc.

    Exit 127 = command-not-found (missing interpreter) → blocking (2). Build-failure
    patterns (case-insensitive) → 2. Otherwise, prefer 3 (test failure) on ambiguity.
    """
    if rc == 0:
        return 0
    if rc == 127:
        return 2
    low = output.lower()
    if _BUILD_RE.search(low):
        return 2
    return 3


def main() -> int:
    # -----------------------------------------------------------------------
    # Gate 1 — UBT pending-record resolution — RETIRED 2026-08-06
    # (shell-spawn-regrowth-gate C7b). Previously presence-detected
    # `bin/check-ubt-build-fresh.sh` cwd-relative and, when present, spawned
    # it via `["bash", ubt_path, ...]` — a bash-binary argv[0] spawn the
    # 2026-08-06 no-shell-spawns ruling does not tolerate. No repo in the
    # local sibling-repo checkout root ships that script (exhaustive
    # `find -iname` found zero matches), and the one plausible consuming
    # repo, example-game-workbench-repo, already retired its own copy in favor of
    # a Python port (`bin/check_ubt_build_fresh.py`, commit 290eaa298) under
    # a path this gate's hyphenated presence-check could never match. A
    # presence-detected gate with no live producer anywhere in reach fires
    # nowhere; RC_UBT stays hardcoded "skipped" for wire-format stability.
    # -----------------------------------------------------------------------
    rc_ubt: object = "skipped"

    # -----------------------------------------------------------------------
    # Gate 2 — Fast-test resolver + invocation
    # -----------------------------------------------------------------------
    _lib_path = _RVC_PATH
    if not os.path.isfile(_lib_path):
        _err(f"[workday-complete-step1] WARN: resolver lib not found at {_lib_path} — fast-test gate skipped.")
        _emit(rc_ubt, "lib-missing")
        return 4

    # Resolve the fast-test command in-process (native port — no bash-lib bridge
    # subprocess spawn). cwd is load-bearing: the resolver reads
    # coordinator.local.md relative to cwd (presence-detection). The resolver
    # prints its own diagnostic stderr live, so no separate forward step here.
    resolve = rvc.resolve_fast_test_cmd(os.getcwd())

    if resolve.returncode == 2:
        # Genuine skip-with-notice (no command configured) — the only resolver
        # non-zero that maps to a non-blocking skip.
        _emit(rc_ubt, "skipped")
        return 0
    if resolve.returncode == 126:
        # Malformed configured value (un-interpretable escaped quote). Blocking,
        # and reported as a CONFIG defect rather than folded into the generic
        # environment/build bucket — the whole cost of the originating incident
        # (project-rag, 2026-07-22) was a config defect wearing "build failure"
        # for a day, so the status word has to name where to look.
        _err("[workday-complete-step1] fast-test: resolver rejected the configured command "
             "(rc=126) — malformed fast_test_cmd, NOT a test or build failure. Fix the value "
             "in coordinator.local.md. Validation gate is BLOCKED.")
        _emit(rc_ubt, "config-malformed")
        return 2
    if resolve.returncode != 0:
        # Any OTHER resolver non-zero is a HARD failure (canonically exit 127:
        # bare `python` token with no python on PATH). Blocking, not a skip.
        _err(f"[workday-complete-step1] fast-test: resolver failed (rc={resolve.returncode}) — "
             "interpreter/environment problem, NOT a skip. Validation gate is BLOCKED.")
        _emit(rc_ubt, "interp-missing")
        return 2

    cmd = resolve.stdout.strip()

    try:
        _fail_on_ambiguous_shell_syntax(cmd)
    except AmbiguousShellSyntax:
        _emit(rc_ubt, "shell-metachar")
        return 2

    # Diff-scoping: when the working tree has changed test files, append
    # them onto the resolved command so this gate runs only those files
    # instead of the whole configured fast tier. Empty changed-test-file
    # set -> behaviour unchanged (scoped_cmd == cmd). See
    # coordinator_core/diff_scoped_tests.py for the "changed test file"
    # definition and the append-only (never rebuild) contract that keeps
    # the `-m '...'` marker selector intact. Scoping only ever appends plain
    # path tokens onto an already-metachar-checked `cmd`, so scoped_cmd does
    # not need a second _fail_on_ambiguous_shell_syntax pass.
    diff_paths = find_changed_test_files(os.getcwd())
    if diff_paths:
        scoped_cmd = append_test_paths(cmd, diff_paths)
        diag(f"changed test file(s) detected -- scoping run to: {', '.join(diff_paths)}")
    else:
        scoped_cmd = cmd

    # Classify the resolved command's SHAPE before running it (R3+R4:
    # cross-repo/inbox/2026-07-25-doe-claude-em-validate-tier-u-shape-
    # ruling.md -- this resolve-and-execute-in-process CLI is the same
    # process-boundary shape as validate-fast-and-packageability.py's
    # `fast` subcommand). Refuse rather than execute when the shape is
    # Tier U and the calling session holds no live Tier-U grant; this CLI
    # only READS a grant, never writes one. Gated on scoped_cmd -- the
    # command actually about to execute -- not the unscoped cmd.
    gate = enforce_tier_u_gate(scoped_cmd, repo_root=os.getcwd())
    if not gate.proceed:
        _err(gate.refusal_message)
        _emit(rc_ubt, "tier-u-refused")
        return 5

    # Strip COORDINATOR_CORE_LAZY_OPS before spawning: cc_invoke's module-top
    # `os.environ.setdefault(...)` (see coordinator/bin/lib/cc_invoke.py) mutates
    # THIS process's environment as a side effect of the earlier
    # `from cc_invoke import resolve_colocated_claude_klabauter_root` import above. Left
    # in place, that flag would leak into the fast-test subprocess and — for a
    # coordinator_core pytest suite that asserts the ops registry at collection
    # time — make eager op-import skip, breaking collection on a green tree.
    # Copy-and-pop, never mutate os.environ in place (that's the exact defect
    # class being fixed here).
    _ft_env = os.environ.copy()
    _ft_env.pop("COORDINATOR_CORE_LAZY_OPS", None)

    ft_rc, ft_content = _run_fast_test_cmd(scoped_cmd, _ft_env)

    if diff_paths and ft_rc == PYTEST_NO_TESTS_COLLECTED:
        # The diff-scoped run named a changed test file the `-m` marker
        # filter then deselected entirely (e.g. it carries only
        # designed_red-marked tests) -- pytest's own "no tests collected"
        # exit code. That is neither a pass nor a failure; fall back to
        # the full configured fast tier so the gate still runs SOMETHING
        # (fail-safe: always toward more testing, never toward silently
        # running zero tests).
        diag(
            "diff-scoped run collected zero tests (pytest rc="
            f"{PYTEST_NO_TESTS_COLLECTED}) -- falling back to the full "
            "configured fast tier."
        )
        gate_full = enforce_tier_u_gate(cmd, repo_root=os.getcwd())
        if not gate_full.proceed:
            _err(gate_full.refusal_message)
            _emit(rc_ubt, "tier-u-refused")
            return 5
        ft_rc, ft_content = _run_fast_test_cmd(cmd, _ft_env)

    rc_validate = ft_rc

    if ft_rc == 0:
        _emit(rc_ubt, rc_validate)
        return 0

    classify_rc = _classify_fast_test_output(ft_content, ft_rc)
    _emit(rc_ubt, rc_validate)
    return classify_rc


if __name__ == "__main__":
    sys.exit(main())
