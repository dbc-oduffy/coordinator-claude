"""gen-launcher-shim.py — emit python-direct Windows launchers for a bin/ entrypoint.

Part of the 2026-07-19 Windows de-bash campaign (Wave 0, unit
w0-launcher-generator). See docs/plans/2026-07-19-debash-coordinator-windows.md.

WHAT THIS IS
    A pure-Python generator (library + CLI, NO shell dependency) that, given a
    bare entrypoint name, emits a paired Windows launcher whose body is
    *python-direct*: it resolves a Python interpreter and runs the co-located
    entrypoint directly via CreateProcess/PATHEXT resolution — it NEVER re-execs
    bash.exe. This is the reusable generator the mass Wave-4 de-shell and the
    w0-missing-shim-enumeration unit consume to give every bare-invoked bin/*
    entrypoint Windows launcher coverage.

WHY python-direct, not bash-routing
    The pre-campaign .cmd shims (coordinator-settings-home.cmd et al.) re-exec
    `bash.exe "%~dp0<forwarder>" %*`. On stock Windows bash.exe is degraded or
    absent — that route BLOCKS Windows users. Once the target entrypoint is a
    pure .py (or a sh/python polyglot that Python can run directly), the correct
    Windows launcher runs `python "%~dp0<name>" %*` with no shell in the middle.

INTERPRETER LADDER (modeled on templates/bin/python3.cmd)
    1. __PYTHON_BIN__ — an absolute interpreter path baked in at install time.
       install-substrate.py substitutes this token with the path
       lib/resolve-python.sh resolved (fast path: skips the `py -3` launcher's
       double-indirection + the Microsoft Store App Execution Alias picker
       risk), OR with the empty string when no interpreter was resolvable at
       install time (e.g. a fresh machine). The literal token only ever survives
       in the generated-but-uninstalled artifact; it is ALWAYS substituted
       (to a path or to empty) before the launcher is executed — exactly the
       contract templates/bin/python3.cmd relies on.
       The baked rung is EXISTENCE-GATED (`if exist` in .cmd, `Test-Path` in
       .ps1), matching `coordinator_core.install.substrate`'s sibling
       forwarder emitter: the ladder falls through when the baked path is
       empty OR names something no longer on disk, so a stale/foreign bake
       is self-healing rather than a permanent hard failure. Without it,
       only an EMPTY bake fell through and a `~/.claude` synced between a
       Mac and a Windows box — every launcher carrying the OTHER platform's
       interpreter path — was unrecoverable.
    2. `where python.exe` — first python.exe on PATH.
    3. `where py` → `py -3` — the Python launcher (last resort; carries the
       Store-alias risk the baked path exists to avoid).
    4. none found → exit 127 with a remediation pointer.

    Each launcher carries its OWN ladder inline: it cannot defer to
    lib/resolve-python.sh, which is bash and unavailable on stock Windows.

USAGE (CLI)
    python gen-launcher-shim.py <name> [--dir DIR] [--no-ps1] [--stdout] [--whoami-bootstrap]
        <name>     bare entrypoint filename (pure .py or extensionless polyglot),
                   e.g. "coordinator-queue-append" or "install-health-run.py".
        --dir DIR  directory to write launcher(s) into (default: cwd).
        --ps1 / --no-ps1
                   also emit <name>.ps1 -- DEFAULT ON (bare `--ps1` is a
                   redundant no-op, kept only for callers that prefer to
                   state the default explicitly). Measured bare-name
                   resolution (pwsh 7.6.4, Windows PowerShell 5.1) shows
                   PowerShell prefers a bare-name's .ps1 sibling over its .cmd
                   sibling universally, so the .ps1 twin upgrades every caller
                   with no call-site change. `--no-ps1` is the explicit
                   override for a caller that deliberately wants .cmd only.
        --stdout   print the .cmd body to stdout instead of writing files
                   (with .ps1 emission on, prints .ps1 too, separated by a
                   form feed; with --whoami-bootstrap, prints the bootstrap
                   body first).
        --whoami-bootstrap
                   ALSO emit <name> itself (extensionless, chmod +x) as the
                   whoami-bootstrap launcher body — see § WHOAMI-BOOTSTRAP
                   EXCEPTION below. Only meaningful for the single named
                   exception, `coordinator-whoami`; do not use for any other
                   entrypoint.

RETIRED: --ensure-unix / ensure_unix_invocable() (2026-07-28)
    This generator used to also carry a `--ensure-unix <py-path>` mode that
    stamped a `#!/usr/bin/env python3` shebang plus a working-tree chmod +x
    onto a bin/ entrypoint, establishing bare-name Unix invocability. PM
    ruling 2026-07-28 (Windows is the P0 primary platform) reclassified
    exactly that shape — env-stripped shebang, extensionless shebang
    executable, git mode 100755 — as a POSIX-only-execution portability
    defect, enforced by `coordinator_core.ops.check_posix_exec_assumptions`.
    Stamping it was therefore manufacturing new guard violations on every
    install (`install-substrate.py` drove this mode over every bin/*.py with
    a co-located .cmd launcher, at install time), directly contradicting the
    new guard. The mode is gone; existing shebang+exec-bit entrypoints are
    tracked as frozen, shrink-only debt in `state/posix-exec-baseline.json`
    rather than actively regenerated. The .cmd/.ps1 launcher classes below
    are unaffected — Windows bare-name invocation was never shebang-based.

USAGE (library)
    import gen_launcher_shim as g
    g.render_cmd("coordinator-queue-append")            -> str  (.cmd body)
    g.render_ps1("coordinator-queue-append")            -> str  (.ps1 body)
    g.render_whoami_bootstrap("coordinator-whoami")      -> str  (bootstrap body)
    g.generate("coordinator-queue-append", out_dir) -> list[Path]  (ps1=True is the default; shown here bare since passing ps1=True explicitly is now redundant)
    g.spec_backlink_for_entry_path("bin/foo.py")        -> str | None

SPEC BACKLINKS (2026-08-03)
    CLAUDE.md makes a spec backlink a REQUIRED exception to the
    no-inline-comments rule (the "RAG-bait exception"). A generated launcher
    could not satisfy it: `bin/claude-klabauter-doctor-probe.cmd` carried the line by
    hand, the fleet regeneration sweep destroyed it, and
    `coordinator_core/test_bin_launcher_parity.py`'s byte-parity guard now
    ENFORCES that destruction. So the backlink is a first-class, OPTIONAL,
    absent-by-default generator input, declared in the sibling registry
    `coordinator/bin/launcher-spec-backlinks.toml` and keyed by the
    entrypoint's repo-relative path.

    Reading it from a registry rather than accepting a `--spec-backlink` flag
    is the whole point: a flag relocates the obligation onto whoever next
    types the regeneration command, which is the "the operator remembers"
    non-discharge the north star rejects. `generate()` and the parity guard
    both resolve the declaration themselves, so a regeneration run by anyone,
    at any time, reproduces the line without being told about it.

    Launchers with no registry row emit NO backlink line and are byte-identical
    to what this generator emitted before the mechanism existed -- see the
    registry file's own header for why the entrypoint docstrings are not the
    source (397 of 533 carry one; deriving from them would rewrite the fleet).

SESSION-CLAIM RECORDING (2026-08-06, DR-276)
    Every launcher `generate()` writes is handed to
    `coordinator_core.session.declared_writes.declare_write`, and `main()`
    opens a declare-write collection (`coordinator_core.cli_entry.
    recording_declared_writes`) around its one write-reaching branch. Without
    this, a generated `.cmd`/`.ps1`/bootstrap file carried no session claim at
    all: this generator is invoked directly as `python3 coordinator/bin/gen-
    launcher-shim.py ...`, never through `ipc.dispatch_message` or a
    `run_op_main`-wrapped trampoline, so the launcher twin landed in
    `session.scope.compute_scope`'s `orphans` set and `ceremony.
    scoped_git_commit` refused an otherwise-ordinary pathspec containing it
    ("orphan — dirty but claimed by no session"). See
    docs/decisions/DR-276-operator-clis-record-session-writes-at-a.md.

WHOAMI-BOOTSTRAP EXCEPTION (2026-07-21 macos-first-class-invocation C9)
    `coordinator-whoami`'s deps (jsonschema, rfc3339-validator, PyYAML) are
    venv-resident per PEP-668 (docs/wiki/install-surface-completeness.md) —
    a bare-python3-shebanged launcher CANNOT `import coordinator_whoami`
    directly. This is the ONE explicitly-named exception to this module's
    otherwise-uniform single-class contract (every other bin/ entrypoint is
    shebang+exec-bit and nothing else — see `ensure_unix_invocable` above).
    `render_whoami_bootstrap()` emits a SECOND kind of body: a
    `#!/usr/bin/env python3` stdlib-only launcher that resolves the
    `coordinator.python` machine-local pin and subprocess-execs
    `<venv-python> -m coordinator_whoami`, never bare-importing the module
    into its own (bare python3) process. Because the bootstrap's OWN
    interpreter stays bare python3, it is itself single-class-shebang-
    compliant — Windows coverage falls out of the EXISTING render_cmd /
    render_ps1 for free (they treat it like any other .py entrypoint); no
    new Windows-side launcher class was needed. Do NOT generalize this
    exception to other entrypoints — every other bin stays the plain
    shebang+exec-bit class this generator already produces.

NEGATIVE SPEC
    - This module NEVER emits a bash re-exec. A launcher that routes through
      bash.exe is out of scope (see coordinator-safe-commit.cmd for the legacy
      bash-routing shape this campaign replaces).
    - The generated .cmd/.ps1 body is NOT hand-edited downstream — regenerate.
    - The launcher name argument is the ENTRYPOINT filename, and the emitted
      launcher basename is derived from it (the .sh/.py suffix is stripped so
      the launcher is <base>.cmd / <base>.ps1). Bare-name PATHEXT resolution
      on Windows keys on the basename without extension.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tomllib
from pathlib import Path

MUTATES = ["coordinator/bin/*.cmd", "coordinator/bin/*.ps1"]

PYTHON_BIN_TOKEN = "__PYTHON_BIN__"

# Repo root, derived from this file's own location (coordinator/bin/<here>) so
# the registry resolves identically whether the generator is invoked as a CLI
# from any cwd or imported by a test that has repointed its own REPO_ROOT.
REPO_ROOT = Path(__file__).resolve().parents[2]

# coordinator_core is engine-owned (this repo) and not on sys.path by default
# for a bare `coordinator/bin/` script invocation -- REPO_ROOT above already IS
# the engine checkout root (this script lives inside it), so this is a plain
# self-location insert, never a machine-local registry lookup (same shape as
# coordinator/bin/seed-marketplace-enabledplugins.py's own coordinator_core
# resolution). Harmless / a no-op when coordinator_core is already importable
# (e.g. a test that loads this module after coordinator_core is on sys.path).
SPEC_BACKLINK_REGISTRY = Path(__file__).resolve().parent / "launcher-spec-backlinks.toml"

# RAW-CMDLINE-PRESERVATION ENTRYPOINTS (2026-08-08, caret-eating .cmd shim defect)
#
# state/bug-backlog/2026-08-08-cmd-exe-shim-eats-the-caret-in-a-git-rev-6679bf76eb8a.yaml
# (DoE-claude): populating a .cmd launcher's %1..%9/%* batch parameters
# silently strips any literal `^` from each argument BEFORE the launcher
# body ever runs — this happens during cmd.exe's OWN command-line parse,
# ahead of anything the generated launcher body could do about it (measured:
# even a bare `echo %*` batch file loses the caret).
#
# CORRECTED (docs/plans/2026-08-15-the-caret-fix-went-to-the-caller-that-never-broke.md):
# the capture below is NOT a fix for this loss — it is caller-conditional, and the
# 2026-08-10 fix and its guard suite validated only the one caller that was never broken.
# cmd.exe strips the caret while parsing its OWN `/c` string, and whether `%CMDCMDLINE%`
# still holds the unstripped text depends on how the SPAWNING process quoted that string:
# it survives iff the entire post-`/c` string is wrapped in one outer quote pair (first and
# last character both `"`). PowerShell emits that shape, so the caret survives into
# `%CMDCMDLINE%` there; git-bash/MSYS and `subprocess.run([...])` list-form do not emit it,
# so the capture on those rungs records text the caret is *already gone from* — the capture
# preserves what `%CMDCMDLINE%` still holds, not what the caller originally typed. A
# launcher whose entrypoint is named here gets ONE extra line exporting that (possibly
# already-mangled) raw text into `_LAUNCHER_RAW_CMDLINE` before invoking Python; the
# entrypoint itself (not this generator) is responsible for classifying the spawn shape and
# refusing rather than trusting an unsound capture (`coordinator/bin/lib/raw_cmdline_recovery.py`).
# This is a SECOND named, narrow, opt-in exception in the same spirit as the WHOAMI-BOOTSTRAP
# EXCEPTION above — do NOT generalize it to every launcher; every entrypoint not named here
# renders byte-identical to before this mechanism existed (see `_cmd_raw_cmdline_block`).
#
# Originating incidents: docs/plans/2026-08-10-caret-fix-on-the-wrong-launcher.md (the fix
# that validated only the PowerShell rung) and
# state/bug-backlog/2026-08-08-cmd-exe-shim-eats-the-caret-in-a-git-rev-6679bf76eb8a.yaml
# (DoE-claude tree). docs/decisions/DR-303-windows-spawn-economics-is-a-fix-not-a-desig.md
# § Residual uncertainty: "Caret recovery ... reasoned from code on macOS" — DR-303 treated
# this as break-class, not as a deferred defect. (Review: coordinator:code-reviewer —
# original phrasing double-"as"; fixed for clarity, meaning unchanged.)
#
# MIRRORED, NOT IMPORTED, against `coordinator_core/install/substrate.py`'s
# `_RAW_CMDLINE_TARGETS` — same caret-eating defect, same keying convention
# (target-filename suffix, not full path), two independent module-load
# surfaces per that module's own docstring (a hyphenated-filename generator
# module has no ordinary `import` form). `scoped-git-commit` and
# `cross-repo-memo` were added to `_RAW_CMDLINE_TARGETS` per
# cross-repo/inbox/2026-08-07-doe-claude-em-cmd-forwarder-drops-everything-
# after-a-newline.md (both take multi-line arguments as a matter of course —
# commit messages, memo bodies) but this set was NOT updated at the time,
# leaving the install path that renders launchers via THIS generator
# directly (rather than via `_write_agent_cmd_forwarder`) still vulnerable
# to the caret-eating defect on those two CLIs. Closed here — see
# `test_bin_launcher_parity.py::test_raw_cmdline_entrypoints_matches_substrate_targets`
# for the drift guard. Extend BOTH sets together, or that test goes red.
#
# 2026-08-28: `scoped-git-commit` dropped from BOTH sets. The CLI itself was
# deleted at 47c78a3a5 ("drop the orphan launchers") under DR-344, but its
# two registrations and four tests were left behind — an entry naming a
# non-existent target renders nothing, so the residue was inert at runtime
# and visible only as a red suite. Retiring one side alone would have
# desynchronised the guarded pair, which is why the substrate-side comment
# had deferred it; both sides go together here.
# 2026-08-19 survey (docs/plans/2026-08-15-the-caret-fix-went-to-the-caller-
# that-never-broke.md's mechanism, extended to the rest of the git-rev-taking
# bin/ surface): `freeze-review-diff.py`, `parallel-review-gate-decision.py`,
# `parallel-review-orthogonality-guard.py`, and `wsc-coverage-gate-runner.py`
# all take an arbitrary git rev/range directly from an agent's typed CLI
# invocation (never defaulted, never composed internally via a Python-list
# subprocess call), so a
# literal `^` (`sha^..sha`, the per-commit predecessor-range shape `--scope
# chain` callers use) is genuinely reachable in normal use on each. Every
# other git-rev/sha-taking bin/ CLI surveyed at the same time (`close-origin-
# stub-on-ship.py --sha`, `install-sentinel-write.py --sha`) takes only a
# single 40-hex SHA with no range/caret shape, and was deliberately NOT
# enrolled -- see this generator's own module docstring § RAW-CMDLINE-
# PRESERVATION ENTRYPOINTS for why this stays a narrow, named, opt-in set.
# MEMBERSHIP RULE, stated once here because it was previously only inferable
# from the incident comments above. A target earns a row when a literal `^`,
# a quote, or an embedded newline is REACHABLE IN NORMAL USE in an argument
# an agent types directly:
#   - an arbitrary git rev/range taken straight from the typed invocation
#     (`sha^..sha`), never defaulted and never composed internally; or
#   - a free-text/multi-line value as a matter of course (commit message,
#     memo body).
# It does NOT earn a row for taking a single 40-hex SHA with no range shape
# (`close-origin-stub-on-ship.py --sha`, `install-sentinel-write.py --sha`),
# and enrolment is not free: it costs every invocation of that target a
# capture file (`lib/entry_point_shim.py`'s own note on the same discipline).
# Narrow and named on purpose -- when a payload is prose rather than a rev,
# prefer the `--<flag>-file <path>` sibling `docs/wiki/windows-first-class.md`
# rules for, which removes the exposure instead of recovering from it.
#
# 2026-08-31: `coordinator-write-review-trail.py` dropped from BOTH sets. Its
# op (`review_trail.write`) was gravestoned K-060 on 2026-08-27 and the file
# is not in the tree; like `scoped-git-commit` before it, an entry naming a
# non-existent target renders nothing, so the residue was inert at runtime and
# invisible to the parity guard -- which compares the two sets to EACH OTHER
# and never to the filesystem. `test_raw_cmdline_members_all_exist` now closes
# that gap; the pair-equality guard alone cannot, because two sets can agree
# perfectly on a file that is gone.
_RAW_CMDLINE_ENTRYPOINTS = frozenset(
    {
        "coordinator/bin/cross-repo-memo.py",
        "coordinator/bin/freeze-review-diff.py",
        "coordinator/bin/parallel-review-gate-decision.py",
        "coordinator/bin/parallel-review-orthogonality-guard.py",
        "coordinator/bin/wsc-coverage-gate-runner.py",
        "coordinator/bin/backlog-grind-assemble.py",
        "coordinator/bin/baton-assemble.py",
        "coordinator/bin/consolidate-assemble.py",
        "coordinator/bin/merge-assemble.py",
        "coordinator/bin/pickup-assemble.py",
        "coordinator/bin/workday-complete-assemble.py",
        "coordinator/bin/workstream-complete-assemble.py",
    }
)

# Suffixes stripped from the entrypoint name to form the launcher basename.
# A launcher for "install-health-run.py" is "install-health-run.cmd"; the .cmd
# invokes the FULL original name ("install-health-run.py") as the entrypoint.
_LAUNCHER_STRIP_SUFFIXES = (".py", ".sh")


def launcher_basename(name: str) -> str:
    """Return the extension-less basename a Windows launcher resolves under.

    "coordinator-queue-append"   -> "coordinator-queue-append"
    "install-health-run.py"      -> "install-health-run"
    "seed-skill-overrides.py"    -> "seed-skill-overrides"
    """
    base = os.path.basename(name)
    for suffix in _LAUNCHER_STRIP_SUFFIXES:
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def load_spec_backlinks(registry: Path = SPEC_BACKLINK_REGISTRY) -> dict[str, str]:
    """Parse the spec-backlink registry into `{entrypoint-rel-path: backlink}`.

    A missing registry is not an error -- it yields an empty mapping, i.e.
    every launcher renders exactly as it did before this mechanism existed.
    That matters beyond convenience: the generator is also read from installed
    copies of this tree, and an install that never shipped the registry must
    still produce launchers, not tracebacks.

    Deliberately NOT cached: `generate()` is called once per launcher by a
    short-lived process, and a cache would make the registry a
    read-once-per-interpreter surface that tests writing their own fixture
    registry could not override.
    """
    try:
        raw = registry.read_bytes()
    except OSError:
        return {}
    table = tomllib.loads(raw.decode("utf-8")).get("backlinks", {})
    return {k: v for k, v in table.items() if isinstance(v, str)}


def spec_backlink_for_entry_path(
    entry_rel_path: str, registry: Path = SPEC_BACKLINK_REGISTRY
) -> str | None:
    """The declared backlink for a repo-relative POSIX entrypoint path.

    Pure lookup, no filesystem probing of the entrypoint itself: the byte-parity
    guard resolves a launcher's declaration from the launcher's own tracked
    path, and must reach the same answer as `generate()` did without depending
    on where the tree happens to be checked out.
    """
    return load_spec_backlinks(registry).get(entry_rel_path)


def entry_rel_path(name: str, out_dir: str | os.PathLike) -> str | None:
    """Repo-relative POSIX path of the entrypoint a launcher in `out_dir` runs.

    Returns None when `out_dir` is outside this repo (the tmp-tree case every
    generator test exercises): a launcher generated outside the repo has no
    registry identity, so it can carry no declared backlink.
    """
    try:
        rel_dir = Path(out_dir).resolve().relative_to(REPO_ROOT)
    except ValueError:
        return None
    return (rel_dir / os.path.basename(name)).as_posix()


def _cmd_backlink_block(spec_backlink: str | None) -> str:
    """The `REM Spec backlink: ...` line, or the empty string when undeclared.

    Empty-by-default is the load-bearing property: interpolating "" leaves the
    surrounding f-string byte-identical to the pre-mechanism body, so the ~410
    launchers that declare nothing do not churn.
    """
    return f"REM Spec backlink: {spec_backlink}\n" if spec_backlink else ""


def _ps1_backlink_block(spec_backlink: str | None) -> str:
    """PowerShell-dialect counterpart of `_cmd_backlink_block` (`#`, not `REM`)."""
    return f"# Spec backlink: {spec_backlink}\n" if spec_backlink else ""


def _cmd_raw_cmdline_block(preserve_raw_cmdline: bool) -> str:
    """The `_LAUNCHER_RAW_CMDLINE` export block, or the empty string when unset.

    Empty-by-default for the same reason as `_cmd_backlink_block`: the ~410
    launchers not named in `_RAW_CMDLINE_ENTRYPOINTS` render byte-identical
    to before this mechanism existed. `%CMDCMDLINE%` is a cmd.exe-only
    builtin — this block has no PowerShell counterpart; `render_ps1` never
    loses the caret in the first place (measured), so only the .cmd dialect
    needs this recovery hook.

    2026-08-14 fix (Raymond Chen-grounded finding, folded in mid-baton): a
    bare `%RANDOM%%RANDOM%.tmp` name is NOT collision-safe across
    invocations, and the collision is cross-session, not cross-second.
    `%RANDOM%` is seeded once per `cmd.exe` process via `srand(time(NULL))`
    -- one-second resolution -- so two launcher invocations starting in the
    SAME second are the SAME `cmd.exe` seed, and draw the IDENTICAL
    `%RANDOM%%RANDOM%` sequence in the identical call order, landing on the
    identical file path. At this machine's 50-70 concurrent-session norm,
    same-second launcher invocations are routine, not a corner case --
    without this fix, one session can silently recover ANOTHER session's
    command line as its own argv (the token-count fallback in
    `raw_cmdline_recovery.recover_windows_argv` does not catch a
    same-shaped colliding invocation), or have its own capture file deleted
    out from under it by whichever process's `os.remove` wins the race.

    Fixed by using `mkdir` as the collision primitive instead of a bare
    filename: Windows' `CreateDirectory` is atomic (a second `mkdir` of the
    same name fails outright, no separate exists-check race window), so a
    `goto`-based retry loop that keeps drawing fresh names until `mkdir`
    actually succeeds is genuinely collision-free -- unlike a
    check-then-write pattern (`if exist ... else echo >file`), which still
    has a TOCTOU race between the check and the write. No spawned process
    (`wmic`, `powershell`) is used to fetch a PID or GUID -- that would
    itself add a process hop to the very launcher this mechanism exists to
    keep thin. Three `%RANDOM%` draws (not two) only widens the per-attempt
    namespace; the retry loop, not the draw count, is what actually
    guarantees uniqueness. The capture file lives inside the freshly-made
    directory so ordinary `echo >` (not itself atomic) never needs to be.
    Not simplified back to a bare filename -- see the incident this
    docstring records.

    NOT `set "_X=%CMDCMDLINE%"` -- measured: cmd.exe's `set` re-strips any
    literal `^` from its own right-hand-side expansion, same as `%*`
    population (a SECOND, independent instance of the caret-eating defect
    this mechanism exists to work around). `echo %CMDCMDLINE%` redirected
    to a file is the one capture form measured to preserve the caret; the
    env var therefore names a FILE PATH (itself caret-free, so an ordinary
    `set` is safe here), not the raw text directly.

    Review: staff-eng (Finding 0) -- the retry loop above was originally an
    unbounded `goto`, which spins forever (silently, stderr swallowed by
    `2>nul`) if `%TEMP%` is full/read-only/ACL-denied, hanging the launcher
    BEFORE Python ever starts on the single hottest path in the system.
    Capture is best-effort everywhere else in this mechanism (a missing/
    unreadable capture file just falls back to the possibly-mangled argv,
    see raw_cmdline_recovery.py) -- only the launcher was treating capture
    as mandatory-or-hang. Bounded to three unrolled attempts behind distinct
    labels (not a counter + `enabledelayedexpansion`, which the block above
    this one deliberately avoids -- see render_cmd's own comment on why).
    On all three `mkdir` attempts failing, control falls through to
    `:_coordinator_raw_cmdline_giveup` WITHOUT setting
    `_LAUNCHER_RAW_CMDLINE_FILE` -- the entrypoint's own
    `recover_windows_argv` already treats a missing env var as a no-op
    fallback to `argv`, so this degrades to best-effort exactly like every
    other failure mode of this mechanism, never a hang.
    """
    if not preserve_raw_cmdline:
        return ""
    return (
        ":_coordinator_raw_cmdline_attempt1\n"
        'set "_LAUNCHER_RAW_CMDLINE_DIR=%TEMP%\\_coordinator_launcher_%RANDOM%%RANDOM%%RANDOM%"\n'
        '2>nul mkdir "%_LAUNCHER_RAW_CMDLINE_DIR%"\n'
        "if not errorlevel 1 goto :_coordinator_raw_cmdline_captured\n"
        ":_coordinator_raw_cmdline_attempt2\n"
        'set "_LAUNCHER_RAW_CMDLINE_DIR=%TEMP%\\_coordinator_launcher_%RANDOM%%RANDOM%%RANDOM%"\n'
        '2>nul mkdir "%_LAUNCHER_RAW_CMDLINE_DIR%"\n'
        "if not errorlevel 1 goto :_coordinator_raw_cmdline_captured\n"
        ":_coordinator_raw_cmdline_attempt3\n"
        'set "_LAUNCHER_RAW_CMDLINE_DIR=%TEMP%\\_coordinator_launcher_%RANDOM%%RANDOM%%RANDOM%"\n'
        '2>nul mkdir "%_LAUNCHER_RAW_CMDLINE_DIR%"\n'
        "if errorlevel 1 goto :_coordinator_raw_cmdline_giveup\n"
        ":_coordinator_raw_cmdline_captured\n"
        'set "_LAUNCHER_RAW_CMDLINE_FILE=%_LAUNCHER_RAW_CMDLINE_DIR%\\cmdline.tmp"\n'
        'echo %CMDCMDLINE%>"%_LAUNCHER_RAW_CMDLINE_FILE%"\n'
        ":_coordinator_raw_cmdline_giveup\n"
    )


def _cmd_localappdata_rung() -> str:
    """The %LOCALAPPDATA% host-local resolution-cache rung shared by every
    `render_cmd` launcher (DR-303 / windows-interpreter-bake-is-empty --
    docs/decisions/DR-303-windows-spawn-economics-is-a-fix-not-a-desig.md).

    Sits between the baked-token check and the `where python.exe` fallback:
    on a host where the bake is empty (macOS-run install, `--setup-only`, or
    a synced `~/.claude` carrying the OTHER platform's baked path), every
    invocation used to re-walk `where`/`findstr` from scratch -- DR-303
    measures that at ~10 processes per op. This rung persists the resolved
    interpreter under `%LOCALAPPDATA%\\coordinator\\python-bin-cache.txt`,
    which never roams/syncs between machines (unlike a bake), so it cannot
    be poisoned the way a synced bake can, and self-heals via the same
    `if exist`/non-empty existence gate the baked rung itself uses.

    ONE shared cache file across every `render_cmd` launcher (not one per
    entrypoint): all of them resolve the identical interpreter on a given
    host, so a single cache primes every launcher after the first cold
    resolution rather than each entrypoint paying its own first-miss cost.
    `coordinator_core.install.substrate._write_agent_cmd_forwarder`
    formerly emitted the same rung, against the same cache file, for the
    settings-home-installed agent-helper forwarder family -- that writer is
    deleted (91771f631d, "the cmd forwarder dies": every install-side name
    gets the native door image or the bare-Python forwarder now, never a
    `.cmd`); this repo-tree generator's own `render_cmd` is unaffected and
    still shares this cache file's naming with nothing left to share it.

    Returns two strings: the read-side block (spliced in ahead of the
    `where python.exe` for-loop) and the write-side block (spliced in behind
    a new `:cache_and_run_baked` label the for-loop's hit now targets).
    """
    read_block = (
        "REM Host-local resolution cache (DR-303 / windows-interpreter-bake-is-empty):\n"
        "REM lives under %LOCALAPPDATA%, which never syncs between machines, so it\n"
        "REM cannot be poisoned by a Mac/Windows-synced settings-home the way a bake\n"
        "REM can. Guarded by `if exist`/non-empty exactly like the bake rung above --\n"
        "REM self-heals the same way when the cached path is stale or foreign.\n"
        "if not defined LOCALAPPDATA goto :skip_cache_read\n"
        'set "_cachefile=%LOCALAPPDATA%\\coordinator\\python-bin-cache.txt"\n'
        'if not exist "%_cachefile%" goto :skip_cache_read\n'
        'set "_cached="\n'
        'set /p _cached=<"%_cachefile%"\n'
        'if "%_cached%"=="" goto :skip_cache_read\n'
        'set "_cached=%_cached:"=%"\n'
        'set "_cachedtest=%_cached:WindowsApps=%"\n'
        'if not "%_cachedtest%"=="%_cached%" goto :skip_cache_read\n'
        'if not exist "%_cached%" goto :skip_cache_read\n'
        'set "_py=%_cached%"\n'
        "goto :run_baked\n"
        ":skip_cache_read\n"
    )
    write_block = (
        ":cache_and_run_baked\n"
        "REM Persist the resolved interpreter for future invocations on THIS host.\n"
        "REM Every writer resolves the same `_py` value (deterministic per machine),\n"
        "REM so a write-write race can only ever race identical content into the\n"
        "REM target. The write happens inside a per-writer temp DIRECTORY (mkdir is\n"
        "REM atomic, unlike a bare %RANDOM% filename), moved into place with `move`\n"
        "REM (atomic same-volume rename, never an in-place write) -- a losing\n"
        "REM writer's move silently no-ops, no retry needed.\n"
        "if not defined LOCALAPPDATA goto :run_baked\n"
        'set "_cachedir=%LOCALAPPDATA%\\coordinator"\n'
        'if exist "%_cachedir%\\" goto :cache_write\n'
        'mkdir "%_cachedir%" 2>nul\n'
        ":cache_write\n"
        'set "_tmpdir=%_cachedir%\\python-bin-cache.%RANDOM%%RANDOM%%RANDOM%.tmp"\n'
        '2>nul mkdir "%_tmpdir%"\n'
        "if not errorlevel 1 goto :cache_write_got_dir\n"
        'set "_tmpdir=%_cachedir%\\python-bin-cache.%RANDOM%%RANDOM%%RANDOM%.tmp"\n'
        '2>nul mkdir "%_tmpdir%"\n'
        "if not errorlevel 1 goto :cache_write_got_dir\n"
        'set "_tmpdir=%_cachedir%\\python-bin-cache.%RANDOM%%RANDOM%%RANDOM%.tmp"\n'
        '2>nul mkdir "%_tmpdir%"\n'
        "if errorlevel 1 goto :run_baked\n"
        ":cache_write_got_dir\n"
        'set "_tmpfile=%_tmpdir%\\python-bin-cache.tmp"\n'
        '>"%_tmpfile%" echo %_py%\n'
        'move /y "%_tmpfile%" "%_cachefile%" >nul 2>nul\n'
        '2>nul rd /s /q "%_tmpdir%"\n'
        "goto :run_baked\n"
    )
    return read_block, write_block


# --- Dispatch-root launcher cache (C15, docs/plans/2026-08-21-the-cli-
# bootstrap-tax-dies-at-the-interpreter-floor.md) -----------------------
#
# THE SHAPE: stamp + `_registry_mtime_pair`'s triple as the composite key,
# carried in the `%LOCALAPPDATA%` self-healing cache, NEVER in any tracked
# `.cmd`/`.ps1` body -- the byte-parity guard over all 393 launchers requires
# that, and a launcher cannot re-bake itself past the next publish (see this
# row's own plan body). `_cmd_localappdata_rung` above is precedent for WHERE
# a resolution-cache value lives, and for NOTHING ELSE -- its validity
# predicate is pure EXISTENCE (`if exist`, non-empty), which is exactly what
# a dispatch-root cache cannot use: a stale root still exists. THE FRESHNESS
# COMPARISON HERE HAPPENS IN PYTHON, AFTER INTERPRETER START, NEVER IN
# cmd.exe -- cmd.exe's timestamp expansion is minute-granular against a
# float `st_mtime` and cannot express this composite key at all.
#
# A SEPARATE cache file from `python-bin-cache.txt`/`python-bin-cache-ps1.txt`
# (different question: "which interpreter" vs "which engine root"), and a
# SEPARATE directory entry from the `.cmd` rung's own key derivation --
# no `.cmd`/`.ps1` rung reads or writes this file; only a Python-side reader
# does (see `read_dispatch_root_cache` below).
_DISPATCH_ROOT_CACHE_DIRNAME = "coordinator"
_DISPATCH_ROOT_CACHE_FILENAME = "dispatch-root-cache.json"

#: Repo-relative path of the engine build stamp DR-328 blessed as an
#: invalidation key -- mirrors `coordinator_core.warm.skew.ENGINE_STAMP_FILENAME`
#: (`coordinator_core/_engine_stamp`) by hand, not by import: that module is
#: the warm-server's own concept of the stamp, this is a read-only consumer
#: of the same on-disk fact, same shape as `_resolve_claude_klabauter.py`'s own
#: `_ENGINE_STAMP_RELATIVE_PARTS` mirror of it.
_ENGINE_STAMP_RELATIVE_PARTS = ("coordinator_core", "_engine_stamp")


def dispatch_root_cache_path() -> Path | None:
    """The `%LOCALAPPDATA%\\coordinator\\dispatch-root-cache.json` path, or
    `None` when `LOCALAPPDATA` is unset (non-Windows / a stripped
    environment) -- mirrors `_cmd_localappdata_rung`'s own guard rather than
    inventing a fallback location this mechanism was never designed to use.
    """
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        return None
    return Path(local) / _DISPATCH_ROOT_CACHE_DIRNAME / _DISPATCH_ROOT_CACHE_FILENAME


def _engine_stamp_bytes(engine_root: Path) -> bytes:
    """Raw bytes of `<engine_root>/coordinator_core/_engine_stamp`, or `b""`
    when absent/unreadable. An absent stamp is a normal state (an unstamped
    working tree, e.g. a live dev checkout) -- never an error; it simply
    participates in the composite key like any other observed value, so an
    unstamped tree's cache entry is invalidated the instant it gains one."""
    stamp_path = engine_root.joinpath(*_ENGINE_STAMP_RELATIVE_PARTS)
    try:
        return stamp_path.read_bytes()
    except OSError:
        return b""


def write_dispatch_root_cache(
    ml_dir: Path, engine_root: Path, root: str, resolution_class: str
) -> None:
    """Persist a gate-resolved `(root, resolution_class)` answer under
    `%LOCALAPPDATA%`, keyed on the engine build stamp PLUS
    `_registry_mtime_pair`'s float triple (AC17) -- the stamp alone misses a
    `machine-local set repos.*` redirect, which changes which engine
    executes WITHOUT touching any stamp (HARD CONSTRAINT 2: that would trade
    a visible latency bug for an invisible staleness one).

    Best-effort: any failure to write is swallowed -- a launcher that never
    gets a bake still resolves the root the slow way, exactly as it does
    today; this is a fast-path accelerator, never a required write. The
    write itself is atomic (temp file + `os.replace`, same-directory rename)
    so a reader never observes a torn file.
    """
    path = dispatch_root_cache_path()
    if path is None:
        return
    from coordinator_core.engine_root import _registry_mtime_pair

    payload = {
        "stamp": _engine_stamp_bytes(engine_root).hex(),
        "registry_mtime": list(_registry_mtime_pair(ml_dir)),
        "root": root,
        "resolution_class": resolution_class,
    }
    tmp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.parent / f".{_DISPATCH_ROOT_CACHE_FILENAME}.{os.getpid()}.tmp"
        tmp_path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
        os.replace(tmp_path, path)
    except OSError:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def read_dispatch_root_cache(ml_dir: Path, engine_root: Path) -> tuple[str, str] | None:
    """Read back a still-fresh dispatch-root bake, or `None` on any miss.

    THE FRESHNESS COMPARISON HAPPENS HERE, IN PYTHON, AFTER INTERPRETER
    START -- never in a generated `.cmd`/`.ps1` body (AC17's clause; see
    this row's own plan body, "THE RESOLUTION HOLDS ONLY WHILE..."). No
    rung of any generated launcher decides hit-vs-miss for this cache before
    starting Python -- only this function does.

    Composite key: engine build stamp bytes (DR-328's invalidation key)
    PLUS `_registry_mtime_pair`'s triple (HARD CONSTRAINT 2 -- a stamp alone
    misses a `machine-local set repos.*` redirect). Both must match the
    cached values for a hit; any mismatch, missing file, or corrupt content
    is a miss -- never an error, since a miss just falls back to the full
    gate walk this cache exists to shortcut around.
    """
    path = dispatch_root_cache_path()
    if path is None:
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    from coordinator_core.engine_root import _registry_mtime_pair

    if payload.get("stamp") != _engine_stamp_bytes(engine_root).hex():
        return None
    if payload.get("registry_mtime") != list(_registry_mtime_pair(ml_dir)):
        return None
    root = payload.get("root")
    resolution_class = payload.get("resolution_class")
    if not isinstance(root, str) or not root:
        return None
    if not isinstance(resolution_class, str) or not resolution_class:
        return None
    return root, resolution_class


def render_cmd(
    name: str,
    python_bin_token: str = PYTHON_BIN_TOKEN,
    spec_backlink: str | None = None,
    preserve_raw_cmdline: bool = False,
) -> str:
    """Render the python-direct .cmd launcher body for entrypoint `name`.

    `python_bin_token` is emitted verbatim as the baked-interpreter value so
    install-substrate.py can token-substitute it (to an absolute path, or to
    the empty string on a no-Python install). Callers wanting a ready-to-run
    artifact for tests may pass an absolute path or "".

    `spec_backlink`, when given, adds ONE `REM Spec backlink: <value>` line to
    the header comment block (see module docstring § SPEC BACKLINKS). It is a
    rendering input, not a lookup: resolution from the registry belongs to the
    caller (`generate()`, or the byte-parity guard), which keeps this function
    pure and lets a test render both variants without touching a file.
    """
    entry = os.path.basename(name)
    tag = launcher_basename(name)
    backlink_block = _cmd_backlink_block(spec_backlink)
    raw_cmdline_block = _cmd_raw_cmdline_block(preserve_raw_cmdline)
    # Review: staff-eng (Finding 2) -- on every path where Python never runs
    # (interpreter-cascade exit /b 127, or the child's own exit code), the
    # freshly `mkdir`-ed raw-cmdline capture dir would otherwise leak under
    # %TEMP% forever: previously a stray .tmp file a `del *.tmp` sweep could
    # clear, now a directory. Cleaned up (best-effort, builtin, no added
    # process) before every exit point -- empty string for launchers not
    # named in _RAW_CMDLINE_ENTRYPOINTS, so their body stays byte-identical.
    raw_cmdline_cleanup = (
        '2>nul rd /s /q "%_LAUNCHER_RAW_CMDLINE_DIR%"\n' if preserve_raw_cmdline else ""
    )
    localappdata_read, localappdata_write = _cmd_localappdata_rung()
    return f"""@echo off
setlocal
REM Windows launcher for {entry} — python-direct (NO bash re-exec).
REM Generated by coordinator/bin/gen-launcher-shim.py — do NOT hand-edit; regenerate.
REM 2026-07-19 Windows de-bash campaign.
REM Contract this artifact carries itself (measured, not doctrine-linked --
REM the doctrine file lives in a sibling repo and is not resolvable from here):
REM   - On bare-name resolution, PowerShell prefers a "{tag}.ps1" sibling of
REM     this file over this "{tag}.cmd" file itself -- if both exist, `{tag}`
REM     typed bare in a pwsh session runs the .ps1, not this .cmd.
REM   - From PowerShell, quote the `--` separator as '--' when invoking this
REM     launcher -- the PowerShell binder eats a bare `--` before this script
REM     ever sees argv, silently dropping it and everything meant to follow it.
REM     Measured against pwsh 7.6.4 -- see coordinator_core/test_bin_launcher_
REM     parity.py::test_argv_fidelity_matrix.
{backlink_block}REM
REM Resolves a Python interpreter and runs the co-located entrypoint "{entry}"
REM directly. install-substrate.py substitutes {python_bin_token} with the
REM absolute interpreter path resolved at install time (fast path: skips the
REM `py -3` double-indirection + the Microsoft Store App Execution Alias
REM picker), or with the empty string when no interpreter was resolvable.
REM Falls back to a host-local %LOCALAPPDATA% resolution cache, then
REM `where python.exe`, then `py -3` -- when the baked value is empty, still
REM the unsubstituted token, OR names a path that is no longer on disk. That
REM fallback is what makes a `~/.claude` synced between a Mac and a Windows
REM box self-healing instead of a permanent rc=3 path-not-found failure: each
REM launcher carries the OTHER platform's interpreter path, and falling back
REM on non-existence is the only repair that is correct on whichever platform
REM is actually running. See DR-303 (docs/decisions/DR-303-windows-spawn-
REM economics-is-a-fix-not-a-desig.md) for the cache rung's own rationale.
REM
REM No `enabledelayedexpansion`: with it on, cmd.exe scans the WHOLE command
REM line -- including whatever %* substitutes in -- for `!...!` tokens before
REM running it, silently mangling any forwarded argument containing a literal
REM `!` (commit messages, JSON payloads, ...). Each interpreter rung below is
REM isolated behind its own `goto` label instead, so `%ERRORLEVEL%` is read
REM outside any parenthesized block (fresh at that point, not frozen at
REM block-parse-time) with no delayed expansion needed.
{raw_cmdline_block}set "_py={python_bin_token}"
if "%_py%"=="{python_bin_token}" set "_py="
if not "%_py%"=="" if exist "%_py%" goto :run_baked
set "_py="

{localappdata_read}
for /f "delims=" %%i in ('where python.exe 2^>nul') do (
    echo %%i| findstr /I /C:"\\WindowsApps\\" >nul
    if errorlevel 1 (
        set "_py=%%i"
        goto :cache_and_run_baked
    )
)

where py >nul 2>&1
if not errorlevel 1 goto :run_py3

echo [{tag}] ERROR: no Python interpreter found (python.exe / py -3). 1>&2
echo [{tag}] Install Python: https://www.python.org/downloads/windows/ 1>&2
{raw_cmdline_cleanup}exit /b 127

{localappdata_write}
:run_baked
"%_py%" "%~dp0{entry}" %*
{raw_cmdline_cleanup}exit /b %ERRORLEVEL%

:run_py3
py -3 "%~dp0{entry}" %*
{raw_cmdline_cleanup}exit /b %ERRORLEVEL%
"""


def _ps1_localappdata_rung() -> tuple[str, str]:
    """PowerShell analog of `_cmd_localappdata_rung` (DR-303 -- see that
    function's docstring for the rung's rationale).

    A SEPARATE cache file from the `.cmd` rung's (`python-bin-cache-ps1.txt`,
    not `python-bin-cache.txt`) -- formerly mirrored
    `_write_agent_ps1_forwarder`'s own choice in
    `coordinator_core.install.substrate` (deleted 2026-08-29, DR-365: the
    install-side `.ps1` leg is condemned outright, see that module's
    gravestone), whose docstring stated the reason: a `.cmd` and a `.ps1`
    invoked with the SAME bare name resolve to DIFFERENT files (PowerShell
    prefers the `.ps1`), so nothing guarantees the two dialects agree on
    interpreter shape, and a shared cache would let one dialect serve a
    value it never itself validated. This repo-tree generator's own
    `render_ps1` keeps the same separation on its own terms.

    `Move-Item -Force` supplies the same atomic-rename guarantee `move` gives
    the `.cmd` rung; a `[System.Guid]` temp name is PowerShell's collision
    primitive here (no `%RANDOM%`-reseed hazard exists in this dialect).

    Returns the read-block (spliced in ahead of the `Get-Command python.exe`
    fallback) and the write-snippet (spliced inside that fallback's success
    branch, before it invokes the resolved interpreter).
    """
    read_block = (
        "# Host-local resolution cache (DR-303 / windows-interpreter-bake-is-empty):\n"
        "# %LOCALAPPDATA% never syncs between machines, unlike the settings-home a\n"
        "# bake is written into, so it cannot be poisoned by a Mac/Windows-synced\n"
        "# home the way a bake can. Mirrors the bake's own Test-Path self-heal: a\n"
        "# cached path that is stale or foreign falls through to re-resolution.\n"
        "# Every step here is in-process (no new spawn on the steady-state path).\n"
        "$_cachefile = $null\n"
        "if ($env:LOCALAPPDATA) {\n"
        "    $_cachefile = Join-Path $env:LOCALAPPDATA 'coordinator\\python-bin-cache-ps1.txt'\n"
        "    if (Test-Path -LiteralPath $_cachefile) {\n"
        "        $_cached = $null\n"
        "        try { $_cached = Get-Content -LiteralPath $_cachefile -TotalCount 1 -ErrorAction SilentlyContinue } catch {}\n"
        "        if ($_cached -and (Test-Path -LiteralPath $_cached)) {\n"
        "            & $_cached $_entry @args\n"
        "            exit $LASTEXITCODE\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    write_snippet = (
        "    if ($_cachefile) {\n"
        "        # Persist for future invocations on THIS host. Every writer resolves\n"
        "        # the same value (deterministic per machine), so a write-write race\n"
        "        # can only race identical content -- and the target is only ever\n"
        "        # mutated via Move-Item -Force (an atomic same-volume rename, never\n"
        "        # an in-place write), so a reader can never observe a torn file. A\n"
        "        # losing writer's move is swallowed (SilentlyContinue): no retry, no\n"
        "        # wait, no added steady-state process either way.\n"
        "        try {\n"
        "            $_cachedir = Split-Path -Parent $_cachefile\n"
        "            if (-not (Test-Path -LiteralPath $_cachedir)) {\n"
        "                New-Item -ItemType Directory -Path $_cachedir -Force -ErrorAction SilentlyContinue | Out-Null\n"
        "            }\n"
        "            $_tmpfile = Join-Path $_cachedir ([System.Guid]::NewGuid().ToString('N') + '.tmp')\n"
        "            [System.IO.File]::WriteAllText($_tmpfile, $_py.Source)\n"
        "            Move-Item -LiteralPath $_tmpfile -Destination $_cachefile -Force -ErrorAction SilentlyContinue\n"
        "        } catch {}\n"
        "    }\n"
    )
    return read_block, write_snippet


def render_ps1(
    name: str,
    python_bin_token: str = PYTHON_BIN_TOKEN,
    spec_backlink: str | None = None,
) -> str:
    """Render the python-direct .ps1 launcher body for entrypoint `name`.

    PowerShell analog of render_cmd — same interpreter ladder, same
    __PYTHON_BIN__ install-time substitution contract, same exit-code
    propagation, and the same optional `spec_backlink` input, emitted in the
    PowerShell comment dialect (`#`) rather than `REM`. `generate()` emits
    this sibling by DEFAULT: measured bare-name resolution (pwsh 7.6.4,
    Windows PowerShell 5.1) shows PowerShell prefers a bare name's .ps1
    sibling over its .cmd sibling universally, not merely in some
    PowerShell-specific coverage gap the .cmd twin already leaves open.
    """
    entry = os.path.basename(name)
    tag = launcher_basename(name)
    backlink_block = _ps1_backlink_block(spec_backlink)
    localappdata_read, localappdata_write = _ps1_localappdata_rung()
    return f"""# {tag}.ps1 — python-direct Windows launcher for {entry} (NO bash re-exec).
# Generated by coordinator/bin/gen-launcher-shim.py — do NOT hand-edit; regenerate.
# 2026-07-19 Windows de-bash campaign.
# Contract this artifact carries itself (measured, not doctrine-linked -- the
# doctrine file lives in a sibling repo and is not resolvable from here):
#   - On bare-name resolution, PowerShell prefers this "{tag}.ps1" file over
#     any co-located "{tag}.cmd" sibling -- `{tag}` typed bare in a pwsh
#     session runs this file, not the .cmd twin.
#   - Quote the `--` separator as '--' when invoking this launcher -- the
#     PowerShell binder eats a bare `--` before this script ever sees argv,
#     silently dropping it and everything meant to follow it. Measured
#     against pwsh 7.6.4 -- see coordinator_core/test_bin_launcher_parity.py
#     ::test_argv_fidelity_matrix.
{backlink_block}#
# Resolves a Python interpreter and runs the co-located entrypoint "{entry}"
# directly. install-substrate.py substitutes {python_bin_token} with the
# absolute interpreter path resolved at install time (or the empty string when
# none was resolvable). Falls back to `python.exe` on PATH, then `py -3` -- when
# the baked value is empty, still the unsubstituted token, OR names a path that
# is no longer on disk. That fallback also tries a host-local %LOCALAPPDATA%
# resolution cache first (see DR-303, docs/decisions/DR-303-windows-spawn-
# economics-is-a-fix-not-a-desig.md) -- what makes a `~/.claude` synced
# between a Mac and a Windows box self-healing instead of a permanent hard
# failure: each launcher carries the OTHER platform's interpreter path, and
# falling back on non-existence is the only repair that is correct on whichever
# platform is actually running.
$ErrorActionPreference = 'Stop'
$_here = Split-Path -Parent $MyInvocation.MyCommand.Path
$_entry = Join-Path $_here '{entry}'
$_pybin = '{python_bin_token}'
if ($_pybin -eq '{python_bin_token}') {{ $_pybin = '' }}
if ($_pybin -ne '' -and -not (Test-Path -LiteralPath $_pybin)) {{ $_pybin = '' }}
if ($_pybin -ne '') {{
    & $_pybin $_entry @args
    exit $LASTEXITCODE
}}
{localappdata_read}$_py = Get-Command python.exe -ErrorAction SilentlyContinue | Where-Object {{ $_.Source -notlike '*\\WindowsApps\\*' }} | Select-Object -First 1
if ($_py) {{
{localappdata_write}    & $_py.Source $_entry @args
    exit $LASTEXITCODE
}}
$_pyl = Get-Command py -ErrorAction SilentlyContinue
if ($_pyl) {{
    & $_pyl.Source -3 $_entry @args
    exit $LASTEXITCODE
}}
[Console]::Error.WriteLine('[{tag}] ERROR: no Python interpreter found (python.exe / py -3).')
[Console]::Error.WriteLine('[{tag}] Install Python: https://www.python.org/downloads/windows/')
exit 127
"""


# Defaults for the single named PEP-668 exception (see module docstring
# § WHOAMI-BOOTSTRAP EXCEPTION). Not used by any other launcher class.
WHOAMI_LAUNCHER_NAME = "coordinator-whoami"
WHOAMI_MODULE = "coordinator_whoami"


def render_whoami_bootstrap(
    name: str = WHOAMI_LAUNCHER_NAME, module: str = WHOAMI_MODULE
) -> str:
    """Render the whoami-bootstrap launcher body for entrypoint `name`.

    The ONE explicitly-named PEP-668 exception to this generator's
    otherwise-uniform single-class contract (see module docstring
    § WHOAMI-BOOTSTRAP EXCEPTION). Unlike render_cmd/render_ps1, this body
    is itself a `#!/usr/bin/env python3` bare-python3 entrypoint — it never
    imports `module` into its own process (D2-26, subprocess-not-bare-
    import). Instead it resolves the `coordinator.python` machine-local pin
    (mirroring lib/resolve-python.sh's pinned-interpreter tier, reimplemented
    here in stdlib Python because that library is bash and unavailable on
    stock Windows) and subprocess-execs `<venv-python> -m <module>`, where
    `module`'s PEP-668-fenced deps are actually importable. An unresolved or
    invalid pin is a hard failure with a remediation pointer — silently
    falling through to bare python3 would defeat the PEP-668 guarantee this
    launcher exists to preserve.
    """
    tag = launcher_basename(name)
    return f'''#!/usr/bin/env python3
"""{tag} — whoami-bootstrap launcher (Unix + Windows, single-class-shebang).

Generated by coordinator/bin/gen-launcher-shim.py --whoami-bootstrap — do NOT
hand-edit; regenerate. The ONE explicitly-named PEP-668 exception to this
generator's otherwise-uniform single-class contract: {module}'s deps
(jsonschema, rfc3339-validator, PyYAML) are venv-resident per PEP-668
(docs/wiki/install-surface-completeness.md), so this bootstrap resolves the
`coordinator.python` machine-local pin and subprocess-execs
`<venv-python> -m {module}` instead of importing {module} directly. This
launcher's OWN interpreter stays bare python3 (stdlib only), so it is
single-class-shebang-compliant like every other bin/ entrypoint and needs no
special Windows handling — the existing python-direct .cmd/.ps1 launchers
this generator emits for any bare-python3-shebanged .py entrypoint cover it
unmodified.

Resolution order (mirrors lib/resolve-python.sh's pinned-interpreter tier):
    1. COORDINATOR_PYTHON env var, if non-empty.
    2. `machine-local get coordinator.python` (machine-local resolved via
       PATH, falling back to the co-located coordinator/bin/machine-local).
A resolved pin is validated (`<pin> -c "import sys"`) before use; an invalid
or absent pin is a hard failure with a remediation pointer.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

_MODULE = {module!r}
_TAG = {tag!r}


def _machine_local_cli() -> str | None:
    # shutil.which() is PATHEXT-aware on Windows (it tries machine-local.cmd,
    # .exe, .bat, ... for a bare "machine-local" query), so the PATH lookup
    # above is already platform-correct. The co-located fallback below is
    # NOT — os.access(path, os.X_OK) does not meaningfully validate
    # executability on Windows (there is no exec bit), so a naive fallback to
    # the bare/extensionless "machine-local" (the bash script) would pass
    # this check and then get handed to subprocess.run() as argv[0], which
    # fails with WinError 193 ("%1 is not a valid Win32 application") — do
    # NOT "simplify" this back to a single os.path.join(here, "machine-local")
    # check; that reintroduces the exact bug this comment documents.
    found = shutil.which("machine-local")
    if found:
        return found
    here = os.path.dirname(os.path.abspath(__file__))
    if os.name == "nt":
        candidate = os.path.join(here, "machine-local.cmd")
        if os.path.isfile(candidate):
            return candidate
        return None
    lib_relative = os.path.join(here, "machine-local")
    if os.path.isfile(lib_relative) and os.access(lib_relative, os.X_OK):
        return lib_relative
    return None


def _resolve_pin() -> str | None:
    env_pin = os.environ.get("COORDINATOR_PYTHON", "").strip()
    if env_pin:
        return env_pin
    cli = _machine_local_cli()
    if not cli:
        _fallback_name = "machine-local.cmd" if os.name == "nt" else "machine-local"
        sys.stderr.write(
            f"{{_TAG}}: machine-local CLI not found "
            f"(checked PATH and co-located {{_fallback_name}}).\\n"
        )
        return None
    try:
        result = subprocess.run(
            [cli, "get", "coordinator.python"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    pin = result.stdout.strip()
    return pin or None


def _pin_is_valid(pin: str) -> bool:
    try:
        return (
            subprocess.run(
                [pin, "-c", "import sys"],
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).returncode
            == 0
        )
    except OSError:
        return False


def main() -> int:
    pin = _resolve_pin()
    if not pin or not _pin_is_valid(pin):
        sys.stderr.write(
            f"{{_TAG}}: no valid coordinator.python interpreter pin found.\\n"
            f"{{_TAG}}: re-run /coordinator:install to build the coordinator venv.\\n"
        )
        return 127
    argv = [pin, "-m", _MODULE, *sys.argv[1:]]
    try:
        os.execv(pin, argv)
    except OSError as exc:
        sys.stderr.write(f"{{_TAG}}: failed to exec {{pin}}: {{exc}}\\n")
        return 127
    return 0  # unreachable on success — execv replaces this process


if __name__ == "__main__":
    sys.exit(main())
'''


def _chmod_executable(path: Path) -> bool:
    """chmod +x semantics: add an execute bit wherever the matching read bit
    is already set (mirrors `chmod +x`, never grants execute where read is
    absent). Returns True iff the working-tree mode actually changed.

    Retained solely for the whoami-bootstrap exception below (§
    WHOAMI-BOOTSTRAP EXCEPTION) — the general shebang+exec-bit stamping this
    helper used to also serve (`ensure_unix_invocable`) was retired
    2026-07-28; see § RETIRED above.
    """
    current = stat.S_IMODE(path.stat().st_mode)
    exec_bits_to_add = (current & 0o444) >> 2
    new_mode = current | exec_bits_to_add
    if new_mode == current:
        return False
    path.chmod(new_mode)
    return True


def generate(
    name: str,
    out_dir: str | os.PathLike,
    ps1: bool = True,
    whoami_bootstrap: bool = False,
) -> list[Path]:
    """Write the launcher(s) for `name` into `out_dir`; return written paths.

    `ps1` defaults to True: measured bare-name resolution (pwsh 7.6.4,
    Windows PowerShell 5.1) shows PowerShell prefers a bare name's .ps1
    sibling over its .cmd sibling universally, so emitting the .ps1 twin
    upgrades every existing caller with no call-site change. Pass
    `ps1=False` as the explicit override for a caller that deliberately
    wants .cmd-only emission.

    `whoami_bootstrap=True` ALSO writes `<base>` itself (extensionless,
    chmod +x) as the whoami-bootstrap launcher body — see module docstring
    § WHOAMI-BOOTSTRAP EXCEPTION. Only meaningful for the single named
    exception, `coordinator-whoami`.

    The spec backlink, if any, is resolved HERE from the sibling registry
    rather than accepted as an argument, so an operator regenerating a
    launcher cannot omit it by not knowing about it (module docstring
    § SPEC BACKLINKS). It applies to both dialects from one declaration.

    Every path actually written is also handed to
    `coordinator_core.session.declared_writes.declare_write` (DR-276) so a
    caller invoking this module in-process inside an open declare-write
    collection (e.g. `coordinator_core.cli_entry.recording_declared_writes`,
    which `main()` below opens for the bare-CLI path) gets those paths
    recorded as its own session's touch claim rather than landing as an
    unclaimed orphan at the `scoped_git_commit` sink. `declare_write` is a
    no-op outside an open collection, so a caller that never opens one (e.g.
    a test importing this module directly) is unaffected.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from coordinator_core.session.declared_writes import declare_write

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = launcher_basename(name)
    written: list[Path] = []

    rel = entry_rel_path(name, out)
    spec_backlink = spec_backlink_for_entry_path(rel) if rel else None
    preserve_raw_cmdline = rel in _RAW_CMDLINE_ENTRYPOINTS if rel else False

    if whoami_bootstrap:
        bootstrap_path = out / base
        bootstrap_path.write_text(render_whoami_bootstrap(name), encoding="utf-8", newline="\n")
        _chmod_executable(bootstrap_path)
        written.append(bootstrap_path)
        declare_write(bootstrap_path)

    cmd_path = out / f"{base}.cmd"
    cmd_path.write_text(
        render_cmd(name, spec_backlink=spec_backlink, preserve_raw_cmdline=preserve_raw_cmdline),
        encoding="utf-8",
        newline="\r\n",
    )
    written.append(cmd_path)
    declare_write(cmd_path)

    if ps1:
        ps1_path = out / f"{base}.ps1"
        ps1_path.write_text(
            render_ps1(name, spec_backlink=spec_backlink),
            encoding="utf-8",
            newline="\r\n",
        )
        written.append(ps1_path)
        declare_write(ps1_path)

    return written


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gen-launcher-shim.py",
        description="Emit python-direct Windows launcher(s) for a bin/ entrypoint.",
    )
    p.add_argument(
        "name",
        nargs="?",
        default=None,
        help="bare entrypoint filename (pure .py or extensionless polyglot)",
    )
    p.add_argument("--dir", default=".", help="output directory (default: cwd)")
    p.add_argument(
        "--ps1",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="also emit <name>.ps1 (default: yes -- PowerShell prefers .ps1 "
        "over .cmd on bare-name resolution; pass --no-ps1 to suppress)",
    )
    p.add_argument("--stdout", action="store_true", help="print body to stdout, do not write files")
    p.add_argument(
        "--whoami-bootstrap",
        action="store_true",
        help="also emit <name> itself as the whoami-bootstrap launcher body "
        "(single named PEP-668 exception — see module docstring; only "
        "meaningful for coordinator-whoami)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.name:
        print("gen-launcher-shim.py: <name> is required", file=sys.stderr)
        return 2
    if args.stdout:
        # Resolved against --dir exactly as generate() would, so --stdout is a
        # faithful preview of the bytes a write would produce rather than a
        # second, backlink-less rendering path.
        rel = entry_rel_path(args.name, args.dir)
        spec_backlink = spec_backlink_for_entry_path(rel) if rel else None
        preserve_raw_cmdline = rel in _RAW_CMDLINE_ENTRYPOINTS if rel else False
        if args.whoami_bootstrap:
            sys.stdout.write(render_whoami_bootstrap(args.name))
            sys.stdout.write("\f")
        sys.stdout.write(
            render_cmd(args.name, spec_backlink=spec_backlink, preserve_raw_cmdline=preserve_raw_cmdline)
        )
        if args.ps1:
            sys.stdout.write("\f")
            sys.stdout.write(render_ps1(args.name, spec_backlink=spec_backlink))
        return 0
    # This module is invoked directly as `python3 coordinator/bin/gen-launcher-
    # shim.py ...` -- it never passes through ipc.dispatch_message or a
    # `run_op_main`-wrapped trampoline, so nothing else opens a declare-write
    # collection for it (DR-276). Opening one HERE, around the only branch
    # that actually writes files, is what turns generate()'s declare_write()
    # calls into a recorded session touch claim instead of a no-op -- deferred
    # import (cli_entry pulls in ipc, which the --stdout preview branch above
    # should not pay for).
    from coordinator_core.cli_entry import recording_declared_writes  # noqa: E402,PLC0415

    # `cwd` here is the process cwd the recorder resolves declared paths
    # against (matching `run_op_main`'s own default) -- NOT `args.dir`. The
    # paths handed to `declare_write` inside `generate()` are already
    # `out_dir`-prefixed (`out / f"{base}.cmd"`, where `out == Path(args.dir)`),
    # so passing `args.dir` here would make the recorder look for e.g.
    # "<args.dir>/<args.dir>/foo.cmd" and silently skip every declaration as
    # "not an existing regular file" -- caught by this chunk's own end-to-end
    # verification, not by inspection.
    with recording_declared_writes():
        written = generate(
            args.name, args.dir, ps1=args.ps1, whoami_bootstrap=args.whoami_bootstrap
        )
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
