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
import signal
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
from cc_invoke import require_colocated_engine_on_path, child_env  # noqa: E402

try:
    _REPO_ROOT = require_colocated_engine_on_path(__file__)
except RuntimeError as _exc:
    print(f"{os.path.basename(__file__)}: engine-root resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)

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
from coordinator_core.testing import suite_mutex  # noqa: E402
from coordinator_core.win_portability import no_console_passthrough_kwargs  # noqa: E402
from coordinator_core.testing.suite_mutex import MUTEX_WAIT_SECS, mutex_owner  # noqa: E402

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


# --------------------------------------------------------------------------
# Process-group teardown on abort (docs/plans/2026-08-13-reap-orphaned-
# execnet-gateways.md, chunk C1) -- when the resolved fast-test command
# spawns `pytest -n auto`, execnet's worker pool are grandchildren of this
# process. subprocess.run's own KeyboardInterrupt path (and a bare SIGTERM
# with no handler) reaps only the direct child, orphaning the pool; execnet
# does register an atexit cleanup (execnet/multi.py:62) but atexit never
# runs on an uncatchable abort. Proven on this host (docs/research/
# spike-verdicts/2026-08-13-execnet-gateway-reap-on-abort.md): putting the
# child in its own process group and killpg-ing that group on a catchable
# signal reaps 2 of 2 orphaned gateways (spike scenarios 2 and 3a).
# --------------------------------------------------------------------------


def _add_process_group_spawn_kwargs(spawn_kwargs: dict) -> None:
    """Mutate `spawn_kwargs` (already carrying env/console-suppression
    kwargs meant for subprocess.Popen) so the child starts in its own
    process group -- the seam `_install_group_teardown` needs to tear the
    whole group down on abort instead of orphaning it.

    POSIX: `start_new_session=True` makes the child's pgid equal its own
    pid (setsid), so `os.killpg(proc.pid, ...)` reaps the whole pool and
    nothing outside it -- proven (spike scenarios 2/3a).

    Windows: `start_new_session` is accepted by `subprocess.Popen.__init__`
    but is unused by CPython's own Windows `_execute_child` (the parameter
    exists only for the POSIX code path), so leaving it set is harmless
    there. `CREATE_NEW_PROCESS_GROUP` is ORed into whatever creationflags
    `no_console_passthrough_kwargs()` already supplied -- this is the
    Windows process-group primitive; the actual kill mechanism is the Job
    Object in `_assign_windows_job_object` below. NOT PROVEN on this host
    (macOS/arm64) -- see that function's docstring.
    """
    spawn_kwargs["start_new_session"] = True
    if os.name == "nt":
        spawn_kwargs["creationflags"] = spawn_kwargs.get("creationflags", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )


def _teardown_process_group(proc: "subprocess.Popen") -> None:
    """Kill ONLY the process group `proc` itself created -- never anything
    else. `_add_process_group_spawn_kwargs` makes `proc`'s pgid equal its
    own pid (POSIX `start_new_session`), so `os.killpg(proc.pid, ...)`
    reaps exactly this runner's pool. Deliberately never matches on the
    execnet command-line signature: 50-70 concurrent LLM sessions share
    this box and peers run xdist here too, and the spike observed four
    gateways under a live peer controller that a signature match would
    have killed.

    Swallows any failure (AC3): a reap that raises must never change the
    run's exit code, and the caller's own `except OSError` rc=127 contract
    for a missing-executable spawn stays byte-identical.

    Defense-in-depth: confirms `proc` is still its own process-group leader
    before signaling. Correct today only because the paired spawn always
    sets `start_new_session=True` (pgid == pid); if a future edit drops
    that kwarg while this teardown stays wired, `proc` would otherwise
    inherit the runner's own pgid and `killpg` would self-kill the
    runner's whole process group. Fails closed: any doubt (including
    `os.getpgid` itself raising because the child already exited) skips
    the signal rather than risking it.
    """
    if os.name == "nt":
        return
    try:
        if os.getpgid(proc.pid) != proc.pid:
            return
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def _install_group_teardown(proc: "subprocess.Popen"):
    """Install SIGTERM/SIGINT handlers that tear down `proc`'s process
    group before this process itself terminates -- the proven POSIX abort
    path (spike scenarios 2/3a). Returns a `restore()` callable that
    reinstates whatever handler was previously installed; call it in a
    `finally` around the wait so the handler installed here never outlives
    the single spawn it guards.

    After tearing the group down, the handler restores the prior
    disposition and re-raises the same signal at itself -- SIGTERM then
    terminates normally (its default disposition), and SIGINT resumes
    whatever the previous handler did (ordinarily Python's own
    `default_int_handler`, raising `KeyboardInterrupt`), so the run's own
    abort semantics are unchanged; only the orphaned pool is now reaped
    first.
    """
    if os.name == "nt":
        return lambda: None

    prev_handlers: dict[int, object] = {}

    def _on_signal(signum, frame):
        _teardown_process_group(proc)
        signal.signal(signum, prev_handlers[signum])
        os.kill(os.getpid(), signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        prev_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, _on_signal)

    def _restore() -> None:
        for sig, handler in prev_handlers.items():
            signal.signal(sig, handler)

    return _restore


def _assign_windows_job_object(proc: "subprocess.Popen"):
    """Put `proc` into a Windows Job Object configured with
    `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so the OS kills every process in
    the job -- including execnet grandchildren -- the moment the job's
    last handle closes, which happens automatically whenever this process
    exits, by any means, not only a caught signal. This is a STRONGER
    mechanism than the POSIX signal-handler path: it does not depend on a
    handler running at all.

    NOT PROVEN on this host -- this repo's dev machine is macOS/arm64
    (docs/research/spike-verdicts/2026-08-13-execnet-gateway-reap-on-abort.md
    § Not executed). Implemented per AC6 and marked unverified here rather
    than assumed equivalent to the proven POSIX leg.

    Returns the job handle (the caller must keep it alive for the child's
    lifetime and close it via `_close_windows_job_object` when done), or
    `None` on any failure -- swallowed, matching AC3: this plumbing must
    never change the run's exit code.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JobObjectExtendedLimitInformation = 9

        class _IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        ):
            kernel32.CloseHandle(job)
            return None

        if not kernel32.AssignProcessToJobObject(job, int(proc._handle)):  # noqa: SLF001 -- no public Windows-handle accessor exists on Popen
            kernel32.CloseHandle(job)
            return None
        return job
    except Exception:
        # AC3: teardown plumbing must never change the run's exit code.
        return None


def _close_windows_job_object(job_handle) -> None:
    """Release a job handle returned by `_assign_windows_job_object`.
    Swallows any failure -- matches AC3, and matches that function's own
    unproven-on-this-host status."""
    if os.name != "nt" or job_handle is None:
        return
    try:
        import ctypes

        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(job_handle)
    except Exception:
        pass


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

    NOT wired to state/test-red/<machine>.yaml (deliberate, not forgotten).
    stdout/stderr are inherited with no pipe (see `spawn_kwargs` below), so
    this site has no captured output to parse into a test-red record --
    piping it would be a live-streaming change to a hot path, ruled out by
    this module's own negative-spec. The sibling site,
    `coordinator/bin/workday-complete-step1-validate.py`, IS wired (commit
    e0fc9a2fd) because it already captures the run's own output. The
    cross-repo test-red commitment (state/cross-repo-commitments/2026-07-25-
    claude-klabauter-to-answer-the-test-red-record-con-bff3653a45f8.yaml) stays OPEN
    as long as this site remains one of the two live callers and is unwired
    -- a /validate cadence run through THIS CLI still writes nothing.

    Spawned in its own process group (`_add_process_group_spawn_kwargs`)
    with a SIGTERM/SIGINT teardown installed for the duration of the wait
    (`_install_group_teardown`) and, on Windows, a kill-on-close Job
    Object (`_assign_windows_job_object`) -- see the module section above
    this function for why (docs/plans/2026-08-13-reap-orphaned-execnet-
    gateways.md, chunk C1).
    """
    argv = shlex.split(cmd)
    # env=child_env(): kept for its settings-home propagation (COORDINATOR_
    # SETTINGS_HOME), not for stripping anything. Until the `import-path-
    # costs-nothing` sprint (C8) this comment described child_env() stripping
    # COORDINATOR_CORE_LAZY_OPS -- cc_invoke's own child_env() no longer
    # writes or strips that var (see coordinator/bin/lib/cc_invoke.py), and
    # lazy op registration is unconditional now, so an inherited value would
    # have zero effect on this repo's own pytest suite's collection (see
    # commit 5943ec01 / coordinator_core/ops/__init__.py for the retired
    # history of that leak).
    spawn_kwargs = dict(
        env=child_env(),
        **no_console_passthrough_kwargs(),
    )
    _add_process_group_spawn_kwargs(spawn_kwargs)
    try:
        proc = subprocess.Popen(argv, **spawn_kwargs)
    except OSError as exc:
        # `bash -c` used to report an unresolvable first token as rc=127;
        # direct exec instead raises (FileNotFoundError on both POSIX and
        # Windows for CreateProcess ERROR_FILE_NOT_FOUND). Preserve the rc=127
        # contract rather than letting this escape as an uncaught traceback.
        print(f"command not found: {argv[0]!r} ({exc})", file=sys.stderr)
        return 127

    job_handle = _assign_windows_job_object(proc)
    restore_signals = _install_group_teardown(proc)
    try:
        return proc.wait()
    finally:
        restore_signals()
        _close_windows_job_object(job_handle)


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

    owner = mutex_owner("suite-mutex")
    with suite_mutex.held(owner, "validate-fast", timeout=MUTEX_WAIT_SECS) as acquired:
        if not acquired:
            current = suite_mutex.holder() or {}
            print(
                "[WARN] suite mutex held by %s for %ss — proceeding unserialized"
                % (current.get("owner", "<unknown>"), int(MUTEX_WAIT_SECS)),
                file=sys.stderr,
            )
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
        with suite_mutex.held(owner, "validate-fast", timeout=MUTEX_WAIT_SECS) as acquired:
            if not acquired:
                current = suite_mutex.holder() or {}
                print(
                    "[WARN] suite mutex held by %s for %ss — proceeding unserialized"
                    % (current.get("owner", "<unknown>"), int(MUTEX_WAIT_SECS)),
                    file=sys.stderr,
                )
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
        **no_console_passthrough_kwargs(),
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
