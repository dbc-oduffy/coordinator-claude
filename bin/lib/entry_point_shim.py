# entry_point_shim.py — in-process loader for the `-assemble` entry points,
# used by coordinator/bin/coordinator-assemble.py to fan multiple
# subcommands into one interpreter instead of one process per subcommand.
#
# Mechanism is settled by measurement (docs/plans/2026-08-16-a-process-per-
# predicate.md, C7): a forwarder that `subprocess.run`s a child dispatcher
# was measured at -0.5123 (51% MORE expensive than the single-process path
# it would replace — two process starts where today's direct-.py invocation
# has one) and is REJECTED. Loading the target module in-process and calling
# its own `main(argv)` — no child process, no second interpreter — was
# measured at -0.0963 (inside the 46% A/A noise floor, i.e. free). This
# module is the in-process shape, applied to the 13 `-assemble` entry
# points; `coordinator/lib/resolve-claude-klabauter/_resolve_claude_klabauter.py :: exec_cli`
# already ships the same choice (`runpy.run_path` in-process on Windows,
# `os.execv` process-replacement on POSIX) for the general forwarder case —
# that module's docstring documents choosing this over "spawning a second
# Python interpreter and subprocess.run-ing the target". This module does
# NOT reinvent that ladder; it is narrower (fixed set of 13 known-shape
# targets under `coordinator/bin/`, no POSIX execv leg needed because the
# caller — coordinator-assemble.py — is itself already the single process
# multiple subcommands share, so there is nothing to replace this process
# WITH).
#
# Target contract (verified against all 13 current `-assemble` `.py` files
# before writing this module): each exposes a module-level `main(...)` where
# 12 of 13 accept `main(argv: list[str]) -> int` and one
# (`workday-start-inbox-blitz-assemble.py`) accepts no arguments at all
# (`main() -> int`, reads no `sys.argv`). `run_target` below probes arity via
# `inspect.signature` rather than hard-coding the one exception, so a future
# 14th target that follows either shape needs no edit here.
#
# Committed, not generated (see plan's § Owed to the parked posix-exec plan,
# "Denominator-collapse hazard" — substrate.py's `_write_agent_forwarder`
# precedent GENERATES forwarders at install time, which would remove
# tracked `.py` entry points from the repo tree and collapse
# `check_posix_exec_assumptions.py`'s scan denominator). This module and
# coordinator-assemble.py are ordinary tracked source files; the 13
# pre-existing `-assemble` `.py`/`.cmd`/`.ps1` launchers are untouched by
# this chunk (no deletion, no regeneration) — nothing about them changes,
# so nothing about the posix-exec baseline's denominator changes either.
#
# Spec backlink: docs/plans/2026-08-16-a-process-per-predicate.md, chunk C8
#
# Routing half (2026-08-16, plan's AC7): the 13 bin/*.py files are now THIN
# SHIMS (each: resolve lib/, `import entry_point_shim`, `sys.exit(
# entry_point_shim.run_target("<name>", sys.argv[1:]))`) rather than
# independent implementations — see § Name-to-callable mapping below.
# Loading a shim BY PATH (the old `_load_module`/`_target_path` shape) would
# recurse: the shim's own `main`/module-exec would call back into
# `run_target` for the same name. So `run_target` now resolves 12 of the 13
# names directly to an ENGINE module + entry callable (never back through
# the shim .py file); only `workday-start-inbox-blitz-assemble` — real
# 496-line logic, not a wrapper, deliberately left unconverted — is still
# loaded by path, and its docstring below states why.
#
# Each of the 12 converted entrypoints' original bin/*.py file body (before
# this change) was read in full and is reproduced here verbatim in effect —
# same import target, same error-message text, same exit codes — so a
# caller of `coordinator/bin/<name>.py` observes byte-identical stdout/
# stderr/exit-code behavior to before, whether invoked directly or through
# `coordinator-assemble.py`.
#
# Spec backlink: docs/plans/2026-08-16-a-process-per-predicate.md, chunk C8
from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Callable, List

BIN_DIR = Path(__file__).resolve().parent.parent

# The 13 `-assemble` entry points this chunk's dispatcher fans in. Plan's
# § Problem counting-rule correction: 13 distinct entry points, not 36 —
# the earlier count double-counted each stem's `.cmd`/`.ps1` launcher
# siblings, which are not separate logic, only separate OS-launch rungs
# over the same `.py`.
ASSEMBLE_TARGETS = (
    "backlog-grind-assemble",
    "baton-assemble",
    "consolidate-assemble",
    "merge-assemble",
    "orient-assemble",
    "pickup-assemble",
    "plan-assemble",
    "review-assemble",
    "sizing-assemble",
    "staff-session-assemble",
    "workday-complete-assemble",
    "workday-start-inbox-blitz-assemble",
    "workstream-complete-assemble",
)

# Targets still resolved BY PATH (loaded from their own bin/*.py file) rather
# than through the module+callable mapping below. `workday-start-inbox-
# blitz-assemble.py` is 496 lines of real ceremony logic (subprocess calls,
# JSON/datetime handling, its own `main() -> int` reading no argv) — not a
# thin wrapper over a `coordinator_core` module like the other 12, so there
# is no "engine module" to point at without relocating that logic, which the
# dispatch brief explicitly declined to force. Left as a by-path target: its
# own bin/*.py file is untouched (not converted to a shim), so no recursion
# risk arises for this one name.
BY_PATH_TARGETS = frozenset({"workday-start-inbox-blitz-assemble"})

_TRANSPORT_FAIL = 3
_USAGE_FAIL = 2


class UnknownTargetError(LookupError):
    """Raised when a requested subcommand name is not one of ASSEMBLE_TARGETS."""


def _record_invocation(name: str) -> None:
    """Record that shim *name* was invoked, for C9's deprecation-window census.

    Answers the question a grep cannot: the plan's § Anti-scope notes that
    "no hits in this repo" is not "no callers", because DoE's ceremony prose
    lives in another tree. So the window closes on observed invocation.

    Three properties, all load-bearing on this hot path:

    - NEVER raises. Wrapped whole, including the import. An observability
      feature that can throw here turns every ceremony on this box into an
      outage; not recording is always the better failure.
    - Imported LAZILY, not at module scope. The engine is not guaranteed to
      be on `sys.path` when a by-path target is loaded, and paying an import
      at module scope would tax callers that never reach a target.
    - Cheap: measured ~0.14ms per call (`coordinator_core.ops.
      shim_usage_census`), against the ~13.6ms `git rev-parse` spawn this
      campaign removes. The census must not cost a meaningful fraction of
      what it is measuring.
    """
    try:
        # ORDERING IS LOAD-BEARING, and getting it wrong was a real defect
        # (found 2026-08-16 during workstream-complete review, introduced by
        # this hook). `coordinator_core.ops.<anything>` triggers that
        # package's `_eager_import_all` over ~206 op modules, and several of
        # them import the top-level `coordinator` package. If this hook runs
        # BEFORE `_import_engine_module` puts the claude-klabauter root on `sys.path`,
        # `coordinator` is unresolvable, `app_session` (and any sibling like
        # it) fails to import, and `coordinator_core.ops` CACHES that failure
        # for the life of the process -- so the op stays unregistered and
        # every ceremony prints an import traceback it never printed before
        # these shims existed. The pre-shim entry points resolved the root
        # first and never hit it.
        #
        # So resolve the root BEFORE importing anything under
        # `coordinator_core.ops`. Cheap: `_cc_invoke_resolve_claude_klabauter_root`
        # is the same resolver `_import_engine_module` uses moments later,
        # and the import itself is already paid for by the engine module
        # every converted target imports anyway.
        resolve_claude_klabauter_root = _cc_invoke_resolve_claude_klabauter_root()
        claude_klabauter_root = resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)

        from coordinator_core.ops.shim_usage_census import record_invocation

        record_invocation(name)
    except Exception:
        pass


def _target_path(name: str) -> Path:
    if name not in ASSEMBLE_TARGETS:
        raise UnknownTargetError(name)
    return BIN_DIR / f"{name}.py"


def _cc_invoke_resolve_claude_klabauter_root():
    """Import and return `cc_invoke._resolve_claude_klabauter_root`, ensuring
    `coordinator/bin/lib` is on `sys.path` first (a caller that reached this
    module via `coordinator-assemble.py` or a converted shim already put it
    there; this is a defensive belt-and-braces insert for any other caller)."""
    lib_dir = str(BIN_DIR / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402

    return _resolve_claude_klabauter_root


def _import_engine_module(dotted: str):
    resolve_claude_klabauter_root = _cc_invoke_resolve_claude_klabauter_root()
    claude_klabauter_root = resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    return importlib.import_module(dotted)


def _simple_entry(name: str, dotted: str) -> Callable[[List[str]], int]:
    """Build the entry callable for one of the 10 single-module targets —
    each original bin/*.py file's `_import_module` + `main(argv)` body was
    exactly this shape (resolve CLAUDE_KLABAUTER_ROOT, import one `coordinator_core`
    module, call its own `main(argv)`), differing only in `name` and
    `dotted`. Reproduces both exception branches' message text and the `3`
    transport-failure exit code verbatim."""

    def _entry(argv: List[str]) -> int:
        try:
            mod = _import_engine_module(dotted)
        except RuntimeError as exc:
            print(f"{name}: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        except ImportError as exc:
            print(f"{name}: {dotted} not importable: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL
        return mod.main(argv)

    return _entry


def _backlog_grind_assemble_entry(argv: List[str]) -> int:
    """Verbatim port of backlog-grind-assemble.py's own `main(argv)` —
    subcommand routing to `coordinator_core.backlog_grind_assemble`
    (brief/mint-run-id) and its `.apply` submodule (apply/drop), which
    is the one target besides workday-complete-assemble that fans out to
    more than a single `mod.main(argv)` call."""
    usage_text = "usage: backlog-grind-assemble brief|mint-run-id|apply|drop <cadence> [...]"

    def _usage() -> int:
        print(usage_text, file=sys.stderr)
        return _USAGE_FAIL

    if not argv:
        return _usage()
    if argv[0] in ("--help", "-h"):
        print(usage_text)
        return 0

    subcommand, rest = argv[0], argv[1:]
    if subcommand not in ("brief", "mint-run-id", "apply", "drop"):
        return _usage()

    try:
        resolve_claude_klabauter_root = _cc_invoke_resolve_claude_klabauter_root()
        claude_klabauter_root = resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        import coordinator_core.backlog_grind_assemble as brief_mod
        import coordinator_core.backlog_grind_assemble.apply as apply_mod
    except RuntimeError as exc:
        print(f"backlog-grind-assemble: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(
            f"backlog-grind-assemble: coordinator_core.backlog_grind_assemble not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    if subcommand in ("brief", "mint-run-id"):
        return brief_mod.main(argv)
    if subcommand == "apply":
        return apply_mod.main_apply(rest)
    return apply_mod.main_drop(rest)


def _workday_complete_assemble_entry(argv: List[str]) -> int:
    """Verbatim port of workday-complete-assemble.py's own `main(argv)` —
    subcommand routing to `coordinator_core.workday_complete.brief`/`.apply`,
    each already owning a complete `main(argv)`.

    Resolution ladder: the original file used `cc_invoke.
    require_colocated_engine_on_path(__file__)` — SELF-LOCATION-FIRST
    (`Path(__file__).parents[2]`), a different rung order from
    `_resolve_claude_klabauter_root`'s env-first ladder used by the other 11 targets.
    Reproduced here with `__file__` standing in for the ORIGINAL
    `coordinator/bin/workday-complete-assemble.py` path (`BIN_DIR /
    "workday-complete-assemble.py"`), not this module's own `__file__` — the
    self-location probe is depth-sensitive (`parents[2]`) and this module
    lives one directory deeper (`coordinator/bin/lib/`), so passing this
    module's own path would probe the wrong ancestor."""
    prog = "workday-complete-assemble"
    if not argv or argv[0] not in ("brief", "apply"):
        print(f"{prog}: usage: {prog} brief|apply [...]", file=sys.stderr)
        return _USAGE_FAIL

    subcmd, rest = argv[0], argv[1:]

    try:
        lib_dir = str(BIN_DIR / "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from cc_invoke import require_colocated_engine_on_path  # noqa: E402

        require_colocated_engine_on_path(str(BIN_DIR / "workday-complete-assemble.py"))
    except RuntimeError as exc:
        print(f"{prog}: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    try:
        if subcmd == "brief":
            from coordinator_core.workday_complete.brief import main as sub_main
        else:
            from coordinator_core.workday_complete.apply import main as sub_main
    except ImportError as exc:
        print(
            f"{prog}: coordinator_core.workday_complete.{subcmd} not importable: {exc}",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    return sub_main(rest)


# Name -> engine entry callable, `argv -> int`, for every target NOT in
# BY_PATH_TARGETS. Derived by reading each of the 13 bin/*.py files' actual
# imports/calls (not guessed from the entry-point name) — see the module
# docstring above and each target's own comment for the file it was derived
# from.
_ENGINE_ENTRIES: dict[str, Callable[[List[str]], int]] = {
    "backlog-grind-assemble": _backlog_grind_assemble_entry,
    "baton-assemble": _simple_entry("baton-assemble", "coordinator_core.baton_assemble"),
    "consolidate-assemble": _simple_entry("consolidate-assemble", "coordinator_core.consolidate_assemble"),
    "merge-assemble": _simple_entry("merge-assemble", "coordinator_core.merge_assemble"),
    "orient-assemble": _simple_entry("orient-assemble", "coordinator_core.orient_assemble"),
    "pickup-assemble": _simple_entry("pickup-assemble", "coordinator_core.pickup_assemble"),
    "plan-assemble": _simple_entry("plan-assemble", "coordinator_core.plan_assemble"),
    "review-assemble": _simple_entry("review-assemble", "coordinator_core.review_assemble"),
    "sizing-assemble": _simple_entry("sizing-assemble", "coordinator_core.sizing_assemble"),
    "staff-session-assemble": _simple_entry("staff-session-assemble", "coordinator_core.staff_session_assemble"),
    "workday-complete-assemble": _workday_complete_assemble_entry,
    "workstream-complete-assemble": _simple_entry("workstream-complete-assemble", "coordinator_core.workstream_complete"),
}


def _load_module(name: str, path: Path):
    # A distinct module name PER CALL (not just per target) so that two
    # in-process invocations of the SAME subcommand within one batched
    # `coordinator-assemble` call each get a fresh module object rather
    # than sharing top-level module state (e.g. a module-level cache) across
    # calls.
    #
    # NOT equivalent to a fresh process, and do not let a later reader think
    # it is: only the ENTRY POINT module is re-executed. Everything it
    # imports stays cached in `sys.modules` across batched calls, so
    # module-level state inside `coordinator_core` (a registry, a memo, a
    # resolved-root cache) IS shared between subcommands in one batch where
    # separate processes gave each its own. That is usually what you want --
    # it is a large part of why batching is 7.17x cheaper -- but a target
    # that relies on dependency state being fresh per invocation will behave
    # differently here than when spawned. `coordinator_core.git.repo_root`'s
    # memo is the specific one to think about, since it is process-lifetime
    # and cwd-keyed by design.
    unique_name = f"_coordinator_assemble_shim__{name}__{id(path)}__{_load_module._counter}"
    _load_module._counter += 1
    spec = importlib.util.spec_from_file_location(unique_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_load_module._counter = 0  # type: ignore[attr-defined]


# --- GATE family (check-*/verify-*/assert-*), chunk C10 ---
#
# 60 entry points, one dispatcher (coordinator-gate.py). Same shim mechanism
# as ASSEMBLE_TARGETS above (in-process, no subprocess), but this family is
# far less uniform than the 13 `-assemble` entries: at least four distinct
# CLI-trampoline shapes coexist (a `cli_entry.run_op_main` wrapper with
# fail-loud vs never-block exit-code conventions; a bare top-level
# `run_op_main` call with no wrapper; fully standalone modules with no
# coordinator_core dependency at all; and multi-hundred-line files carrying
# real logic inline). Forcing every name through one mapping shape risks
# silently changing a fail-exit code or an error-message string this
# chunk's own non-negotiable ("identical argv contract and exit code")
# forbids changing.
#
# So: convert to GATE_ENGINE_ENTRIES only names whose full `coordinator/
# bin/<name>.py` body was read in full this dispatch and reproduced here
# verbatim in effect (same shape as ASSEMBLE_TARGETS' _simple_entry/
# _backlog_grind_assemble_entry above). Every other name stays in
# GATE_BY_PATH_TARGETS — its own bin/*.py file is left completely
# unconverted (not shimmed), same as `workday-start-inbox-blitz-assemble`
# above, so there is no risk of silently drifting a contract nobody
# individually verified this dispatch. This is not a permanent shape: a
# later pass that reads and verifies the remaining ~55 files' exact
# exit-code/argv contracts can promote them the same way.
GATE_TARGETS = (
    "assert-cwd",
    "assert-no-dangling-plan-backlinks",
    "assert-no-terminal-plans-in-live",
    "assert-plan-sizing-citation",
    "check-arch-audit-staleness",
    "check-atlas-watch-drift",
    "check-auto-memory-drained",
    "check-auto-reconcile",
    "check-bin-sh-polyglot",
    "check-competitor-positioning-nudge",
    "check-deferral-orphan-memo",
    "check-deferral-partial-strangle",
    "check-description-length",
    "check-em-environment",
    "check-engine-drift",
    "check-forwarder-drift",
    "check-global-doctrine-mirror",
    "check-harvest-debt",
    "check-install-divergence",
    "check-install-doc-payload",
    "check-machine-local-regeneratability",
    "check-machine-path-leak",
    "check-claude-klabauter-doctor-sentinel",
    "check-mcp-versions",
    "check-multi-event-hook-hardcoded-event",
    "check-no-illegal-paths",
    "check-no-monolith-completion-append",
    "check-pcli-drift-gate",
    "check-persona-slug-leak",
    "check-plugin-drift",
    "check-posix-exec-assumptions",
    "check-rag-state",
    "check-registry-codename-leak",
    "check-schema-version-bump",
    "check-shipped-on-main",
    "check-sh-suffix-polyglot",
    "check-sidecar-fill",
    "check-surface-inline-budget",
    "check-version-consistency",
    "check-weekly-staleness",
    "check-workstream-complete-deletion-blocks",
    "check-wsc-inline-budget",
    "verify-arch-audit-atlas-refresh",
    "verify-coverage",
    "verify-dist-publish-repo-sync",
    "verify-doe-root-seam-sync",
    "verify-no-console-flash",
    "verify-no-powershell-flash",
    "verify-orientation-cache-sync",
    "verify-parallel-review-lens-orthogonality",
    "verify-ps51-clean",
    "verify-publish-targets-portable-sync",
    "verify-schema-registry-sync",
    "verify-skill-anchor-links",
    "verify-snippet-registry-consistency",
    "verify-snippet-sync",
    "verify-subagent-sandbox-preamble-sync",
    "verify-templates-bin-sync",
    "verify-templates-setup-sync",
    "verify-ue-overrides",
)

assert len(GATE_TARGETS) == 60, f"expected 60 gate targets, counted {len(GATE_TARGETS)}"


def _run_op_main_entry(name: str, dotted: str, fail_exit: int = 1) -> Callable[[List[str]], int]:
    """Reproduce the `cli_entry.run_op_main` CLI-trampoline shape shared by
    `assert-no-dangling-plan-backlinks.py`, `assert-plan-sizing-citation.py`,
    and `check-em-environment.py` (each read in full and confirmed identical
    up to `name`/`dotted`/`fail_exit`): resolve CLAUDE_KLABAUTER_ROOT via cc_invoke's
    ladder, import `coordinator_core.cli_entry.run_op_main`, call it with the
    op's dotted module path. `fail_exit` reproduces each file's own
    transport-failure exit code — 1 for the fail-loud gates, 0 for
    check-em-environment's never-block orientation banner."""

    def _entry(argv: List[str]) -> int:
        try:
            resolve_claude_klabauter_root = _cc_invoke_resolve_claude_klabauter_root()
            claude_klabauter_root = resolve_claude_klabauter_root()
            if claude_klabauter_root not in sys.path:
                sys.path.insert(0, claude_klabauter_root)
            from coordinator_core.cli_entry import run_op_main
        except RuntimeError as exc:
            print(f"{name}.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
            return fail_exit
        except ImportError as exc:
            print(f"{name}.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
            return fail_exit
        try:
            return run_op_main(dotted, list(argv))
        except ImportError as exc:
            print(f"{name}.py: {dotted} not importable: {exc}", file=sys.stderr)
            return fail_exit

    return _entry


def _check_posix_exec_assumptions_entry(argv: List[str]) -> int:
    """Verbatim port of check-posix-exec-assumptions.py's own module body:
    no wrapper error-handling (the original imports `run_op_main` at module
    scope, unguarded, and calls `sys.exit(run_op_main(...))` directly) — the
    only GATE_TARGETS member shaped this way among the ones converted here."""
    from coordinator_core.cli_entry import run_op_main

    return run_op_main("coordinator_core.ops.check_posix_exec_assumptions", list(argv))


def _check_pcli_drift_gate_entry(argv: List[str]) -> int:
    """Verbatim port of check-pcli-drift-gate.py's own `main(argv)` — the one
    converted GATE_TARGETS member with its own argv validation (rejects any
    arguments), a distinct transport-failure exit code (2, not 1/0), and a
    dedicated preflight `importlib.import_module` probe on the op module
    (kept SEPARATE from the `run_op_main` call per that file's own review
    comment: only a genuine module-resolution failure should produce the
    "not importable" diagnostic; an ImportError raised from inside the op's
    own execution must propagate uncaught)."""
    _EXIT_ERROR = 2
    argv = list(argv)
    if argv:
        print(f"check-pcli-drift-gate.py: unexpected argument(s): {' '.join(argv)}", file=sys.stderr)
        return _EXIT_ERROR

    try:
        resolve_claude_klabauter_root = _cc_invoke_resolve_claude_klabauter_root()
        claude_klabauter_root = resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        from coordinator_core.cli_entry import run_op_main
    except RuntimeError as exc:
        print(f"check-pcli-drift-gate.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    except ImportError as exc:
        print(f"check-pcli-drift-gate.py: coordinator_core.cli_entry not importable: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    try:
        importlib.import_module("coordinator_core.ops.check_pcli_drift_gate")
    except ImportError as exc:
        print(
            f"check-pcli-drift-gate.py: coordinator_core.ops.check_pcli_drift_gate not importable: {exc}",
            file=sys.stderr,
        )
        return _EXIT_ERROR

    return run_op_main("coordinator_core.ops.check_pcli_drift_gate", [])


# Name -> engine entry callable for the subset of GATE_TARGETS whose bin/
# <name>.py body was read in full and reproduced verbatim above. Every
# GATE_TARGETS name NOT a key here is in GATE_BY_PATH_TARGETS instead.
GATE_ENGINE_ENTRIES: dict[str, Callable[[List[str]], int]] = {
    "assert-no-dangling-plan-backlinks": _run_op_main_entry(
        "assert-no-dangling-plan-backlinks",
        "coordinator_core.ops.assert_no_dangling_plan_backlinks",
        fail_exit=1,
    ),
    "assert-plan-sizing-citation": _run_op_main_entry(
        "assert-plan-sizing-citation",
        "coordinator_core.ops.assert_plan_sizing_citation",
        fail_exit=1,
    ),
    "check-em-environment": _run_op_main_entry(
        "check-em-environment",
        "coordinator_core.ops.check_em_environment",
        fail_exit=0,
    ),
    "check-posix-exec-assumptions": _check_posix_exec_assumptions_entry,
    "check-pcli-drift-gate": _check_pcli_drift_gate_entry,
}

# Every other GATE_TARGETS name: resolved BY PATH from its own untouched
# bin/*.py file, same mechanism as ASSEMBLE_TARGETS' BY_PATH_TARGETS above
# (in-process `_load_module` + SystemExit-catching `main` probe below) — no
# subprocess, so the fan-in win (C7's 7.17x) still applies to these; only
# the routing indirection (module dotted-path instead of file path) is
# deferred pending individual verification of each file's exact contract.
GATE_BY_PATH_TARGETS = frozenset(set(GATE_TARGETS) - set(GATE_ENGINE_ENTRIES))


def _gate_target_path(name: str) -> Path:
    if name not in GATE_TARGETS:
        raise UnknownTargetError(name)
    return BIN_DIR / f"{name}.py"


def run_gate_target(name: str, argv: List[str]) -> int:
    """Run one of the 60 GATE_TARGETS entry points in-process and return its
    exit code. `argv` excludes the subcommand name itself.

    Unlike `run_target` above (whose 13 ASSEMBLE_TARGETS members' `main`
    always RETURNS an int), several GATE_TARGETS members' `main()` calls
    `sys.exit(code)` internally and returns None — reproducing that call
    in-process inside a batched `coordinator-gate` invocation would raise
    SystemExit and kill the rest of the batch. So the BY_PATH branch here
    catches SystemExit and treats `.code` (default 0, coerced to 0 for a
    non-int/None code, matching Python's own `sys.exit()` convention) as the
    return value, on top of the plain-`return`-value probe `run_target`
    already does.
    """
    if name not in GATE_TARGETS:
        raise UnknownTargetError(name)

    _record_invocation(name)

    if name in GATE_ENGINE_ENTRIES:
        # Review: code-reviewer — sys.argv asymmetry, audited empirically.
        # Grepped run_op_main and all 5 GATE_ENGINE_ENTRIES op modules
        # (assert_no_dangling_plan_backlinks, assert_plan_sizing_citation,
        # check_em_environment, check_posix_exec_assumptions,
        # check_pcli_drift_gate) for `sys.argv`: each takes argv as a
        # parameter; the only sys.argv reads are inside
        # `if __name__ == "__main__":` guards, never reached here. No fix
        # needed today; re-grep before promoting a 6th GATE target.
        return int(GATE_ENGINE_ENTRIES[name](list(argv)))

    path = _gate_target_path(name)
    original_argv = sys.argv
    try:
        sys.argv = [str(path)] + list(argv)
        module = _load_module(name, path)
        main_fn = getattr(module, "main", None)
        if main_fn is None:
            raise AttributeError(f"{path} has no module-level main()")
        params = inspect.signature(main_fn).parameters
        try:
            result = main_fn(list(argv)) if params else main_fn()
        except SystemExit as exc:
            code = exc.code
            if code is None:
                return 0
            if isinstance(code, int):
                return code
            print(str(code), file=sys.stderr)
            return 1
        return 0 if result is None else int(result)
    finally:
        sys.argv = original_argv


def run_target(name: str, argv: List[str]) -> int:
    """Run the named `-assemble` entry point in-process and return its exit
    code. `argv` excludes the subcommand name itself (mirrors `sys.argv[1:]`
    for direct invocation of the target `.py`).

    Two resolution shapes, by name:
      - `name in BY_PATH_TARGETS` (currently just
        `workday-start-inbox-blitz-assemble`): loaded BY PATH from its own
        bin/*.py file, same as before this module gained the routing half —
        untouched, not converted to a shim, so no recursion risk.
      - every other name: resolved via `_ENGINE_ENTRIES[name]`, an engine
        module + entry callable, NEVER by loading `coordinator/bin/<name>.py`
        — that file is now itself a thin shim calling back into this
        function, so loading it here would recurse.
    """
    if name not in ASSEMBLE_TARGETS:
        raise UnknownTargetError(name)

    _record_invocation(name)

    if name in BY_PATH_TARGETS:
        path = _target_path(name)
        original_argv = sys.argv
        try:
            sys.argv = [str(path)] + list(argv)
            module = _load_module(name, path)
            main_fn = getattr(module, "main", None)
            if main_fn is None:
                raise AttributeError(f"{path} has no module-level main()")
            params = inspect.signature(main_fn).parameters
            if params:
                return int(main_fn(list(argv)))
            return int(main_fn())
        finally:
            sys.argv = original_argv

    # Review: code-reviewer — sys.argv asymmetry, audited empirically. This
    # branch, unlike BY_PATH_TARGETS above, never sets sys.argv before
    # calling the target. Grepped all 12 engine-mapped ASSEMBLE_TARGETS
    # modules (coordinator_core.{backlog_grind_assemble,baton_assemble,
    # consolidate_assemble,merge_assemble,orient_assemble,pickup_assemble,
    # plan_assemble,review_assemble,sizing_assemble,staff_session_assemble,
    # workday_complete.{brief,apply},workstream_complete}) for `sys.argv`:
    # every module-level `main(argv)` takes argv as a parameter and does not
    # read sys.argv itself; the only `sys.argv` reads found are inside
    # `if __name__ == "__main__":` guards (never reached when called as a
    # library function) and workday_complete/apply.py's and
    # workstream_complete/apply.py's OWN internal splice for the
    # zero-arg-trampoline scripts THEY dispatch to (unrelated to this
    # dispatcher's own argv passing — already save/restore in a finally).
    # No fix needed today; re-grep before adding a 13th engine-mapped
    # target.
    entry = _ENGINE_ENTRIES[name]
    return int(entry(list(argv)))
