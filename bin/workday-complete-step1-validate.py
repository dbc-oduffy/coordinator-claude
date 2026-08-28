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
import signal
import subprocess
import sys
from pathlib import Path

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
import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
from cc_invoke import require_colocated_engine_on_path  # noqa: E402

try:
    _REPO_ROOT = require_colocated_engine_on_path(__file__)
except RuntimeError as _exc:
    print(f"{os.path.basename(__file__)}: engine-root resolution failed: {_exc}", file=sys.stderr)
    sys.exit(1)

from coordinator_core.diff_scoped_tests import (  # noqa: E402
    PYTEST_NO_TESTS_COLLECTED,
    append_test_paths,
    diag,
    find_changed_test_files,
)
from coordinator_core.ops.test_red_record import (  # noqa: E402
    parse_failing_nodeids,
    write_test_red_record,
)
from coordinator_core.session.tier_u_gate import enforce_tier_u_gate  # noqa: E402
from coordinator_core.testing import suite_mutex  # noqa: E402
from coordinator_core.win_portability import no_console_creationflags  # noqa: E402
from coordinator_core.testing.suite_mutex import MUTEX_WAIT_SECS, mutex_owner  # noqa: E402

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
# signal reaps 2 of 2 orphaned gateways (spike scenarios 2 and 3a). Mirrors
# validate-fast-and-packageability.py's copy of this same mechanism --
# the two ceremony spawn sites are independent CLIs, no shared import
# between them, so the mechanism is duplicated rather than factored out
# (matches this file's existing duplication of _fail_on_ambiguous_shell_
# syntax and _SHELL_METACHAR_RE against that sibling file).
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
    `no_console_creationflags()` already supplied -- this is the Windows
    process-group primitive; the actual kill mechanism is the Job Object
    in `_assign_windows_job_object` below. NOT PROVEN on this host
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
    run's exit code, and the existing rc=127 command-not-found contract
    stays byte-identical.

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

    Spawned in its own process group (`_add_process_group_spawn_kwargs`)
    with a SIGTERM/SIGINT teardown installed for the duration of the wait
    (`_install_group_teardown`) and, on Windows, a kill-on-close Job
    Object (`_assign_windows_job_object`) -- see the module section above
    those functions for why (docs/plans/2026-08-13-reap-orphaned-execnet-
    gateways.md, chunk C1).
    """
    _err(f"[workday-complete-step1] fast-test: running: {cmd}")
    argv = shlex.split(cmd)
    spawn_kwargs = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        **no_console_creationflags(),
    )
    _add_process_group_spawn_kwargs(spawn_kwargs)
    try:
        proc = subprocess.Popen(argv, **spawn_kwargs)
    except OSError as exc:
        # `bash -c` used to report an unresolvable first token as rc=127 with
        # "command not found" on stdout/stderr; direct exec instead raises
        # (FileNotFoundError on both POSIX and Windows for CreateProcess
        # ERROR_FILE_NOT_FOUND). Preserve the rc=127 contract
        # _classify_fast_test_output already keys off of, rather than letting
        # this escape as an uncaught traceback.
        ft_content = f"[workday-complete-step1] fast-test: command not found: {argv[0]!r} ({exc})\n"
        ft_rc = 127
        sys.stderr.write(ft_content)
        sys.stderr.flush()
        return ft_rc, ft_content

    job_handle = _assign_windows_job_object(proc)
    restore_signals = _install_group_teardown(proc)
    try:
        stdout, stderr = proc.communicate()
    finally:
        restore_signals()
        _close_windows_job_object(job_handle)
    ft_content = (stdout or "") + (stderr or "")
    ft_rc = proc.returncode
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


def _git_head_sha() -> str:
    """Best-effort ``git rev-parse HEAD`` against cwd. Any failure (detached
    tooling, non-repo cwd, missing git) yields ``"unknown"`` -- this feeds
    the test-red record's ``sha`` field, which is emitter-owned and
    diagnostic only; it must never be allowed to raise into the caller.
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=10,
            **no_console_creationflags(),
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or "unknown"
    except Exception:
        pass
    return "unknown"


def _emit_test_red_record(ft_rc: int, ft_content: str, classify_rc: int) -> None:
    """Write ``state/test-red/<machine>.yaml`` (tier ``fast``) from THIS run's
    already-captured (rc, combined stdout+stderr) -- never a second pytest
    invocation (coordinator_core.ops.test_red_record's own negative-spec).

    Isolation boundary (AC2 of the wiring task): this function must NEVER be
    able to change `main()`'s return value or raise past its own call site.
    Every exception -- MutateAbort (stale-run monotonic guard, an expected
    benign race under concurrent sessions), a locked/read-only state/ dir,
    a YAML parse error on a hand-edited record, anything -- is caught here
    and LOGGED to stderr (not silenced): this diagnostic stream already
    carries non-blocking WARNs (see the suite-mutex WARN above), so one more
    loud-but-non-blocking line matches the file's existing posture rather
    than failing silently, which would leave a stale/missing record with no
    trace of why.
    """
    try:
        # DR-276: `write_test_red_record` is a library function (not an op
        # `main(argv)` -- no op entrypoint to route through `run_op_main`),
        # so the write it performs is wrapped in `recording_declared_writes()`
        # with an explicit `declare_write()` at the write site, per
        # cli_entry's documented carve-out for a CLI that owns its own body
        # (see gen-launcher-shim.py's `main()`). Kept inside this function's
        # existing try/except -- any failure here (including an import
        # failure) is swallowed by the same isolation-boundary contract
        # (AC2) that already governs this function.
        from coordinator_core.cli_entry import recording_declared_writes
        from coordinator_core.machine_resolver import compute_machine
        from coordinator_core.session.declared_writes import declare_write

        outcome = "green" if ft_rc == 0 else ("build-failure" if classify_rc == 2 else "test-failures")
        runner, failing = parse_failing_nodeids(ft_content)
        with recording_declared_writes(cwd=_REPO_ROOT):
            write_test_red_record(
                repo_root=Path(_REPO_ROOT),
                tier="fast",
                sha=_git_head_sha(),
                exit_code=ft_rc,
                outcome=outcome,
                runner=runner,
                failing=failing,
            )
            # Review: coordinator:code-reviewer — this recomputes the same
            # `state/test-red/<machine>.yaml` path `write_test_red_record`
            # (coordinator_core/ops/test_red_record.py) just wrote, because
            # that function doesn't return the path it wrote. The two
            # computations must stay in agreement; if either side's
            # machine-resolution logic changes independently, this
            # declare_write() call silently drifts out of sync with the
            # actual write site.
            record_path = Path(_REPO_ROOT) / "state" / "test-red" / f"{compute_machine()}.yaml"
            declare_write(record_path)
    except Exception as exc:  # noqa: BLE001 -- must never affect the validate verdict/exit code
        _err(f"[workday-complete-step1] test-red record: write failed ({exc!r}) — continuing.")


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

    # `import-path-costs-nothing` sprint (C8): this used to strip
    # COORDINATOR_CORE_LAZY_OPS before spawning, defending against cc_invoke's
    # former module-top `os.environ.setdefault(...)` (see
    # coordinator/bin/lib/cc_invoke.py) mutating THIS process's environment as
    # a side effect of the earlier `from cc_invoke import
    # resolve_colocated_claude_klabauter_root` import above. cc_invoke.py no longer
    # writes that var at all, and lazy op registration is unconditional now
    # (nothing reads it either — see coordinator_core/ops/__init__.py), so an
    # inherited value would have zero effect on the fast-test subprocess's
    # own collection. `.copy()` is kept: the fast-test subprocess still gets
    # its own env object rather than sharing this process's, for the usual
    # reason a spawn shouldn't hand a child a live-mutable dict.
    _ft_env = os.environ.copy()

    owner = mutex_owner("suite-mutex")
    with suite_mutex.held(owner, "workday-complete-step1", timeout=MUTEX_WAIT_SECS) as acquired:
        if not acquired:
            current = suite_mutex.holder() or {}
            _err(
                "[workday-complete-step1] [WARN] suite mutex held by %s for %ss — "
                "proceeding unserialized"
                % (current.get("owner", "<unknown>"), int(MUTEX_WAIT_SECS))
            )
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
        with suite_mutex.held(owner, "workday-complete-step1", timeout=MUTEX_WAIT_SECS) as acquired:
            if not acquired:
                current = suite_mutex.holder() or {}
                _err(
                    "[workday-complete-step1] [WARN] suite mutex held by %s for %ss — "
                    "proceeding unserialized"
                    % (current.get("owner", "<unknown>"), int(MUTEX_WAIT_SECS))
                )
            ft_rc, ft_content = _run_fast_test_cmd(cmd, _ft_env)

    rc_validate = ft_rc

    if ft_rc == 0:
        _emit_test_red_record(ft_rc, ft_content, 0)
        _emit(rc_ubt, rc_validate)
        return 0

    classify_rc = _classify_fast_test_output(ft_content, ft_rc)
    _emit_test_red_record(ft_rc, ft_content, classify_rc)
    _emit(rc_ubt, rc_validate)
    return classify_rc


if __name__ == "__main__":
    sys.exit(main())
