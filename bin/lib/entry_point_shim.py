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
# module is the in-process shape, applied to the 14 `-assemble` entry
# points; `coordinator/lib/resolve-claude-klabauter/_resolve_claude_klabauter.py :: exec_cli`
# already ships the same choice (`runpy.run_path` in-process on Windows,
# `os.execv` process-replacement on POSIX) for the general forwarder case —
# that module's docstring documents choosing this over "spawning a second
# Python interpreter and subprocess.run-ing the target". This module does
# NOT reinvent that ladder; it is narrower (fixed set of 14 known-shape
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
# `run_target` for the same name. So `run_target` now resolves 13 of the 14
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

import contextlib
import importlib
import importlib.util
import inspect
import io
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional

BIN_DIR = Path(__file__).resolve().parent.parent

ASSEMBLE_TARGETS = (
    "backlog-grind-assemble",
    "baton-assemble",
    "consolidate-assemble",
    "merge-assemble",
    "orient-assemble",
    "pickup-assemble",
    "plan-assemble",
    "quick-wrap-assemble",
    "review-assemble",
    "sizing-assemble",
    "staff-session-assemble",
    "workday-complete-assemble",
    "workday-start-inbox-blitz-assemble",
    "workstream-complete-assemble",
)

BY_PATH_TARGETS = frozenset({"workday-start-inbox-blitz-assemble"})

_TRANSPORT_FAIL = 3
_USAGE_FAIL = 2

# Targets whose argv can carry a JSON payload (`--decisions <json>`), and so
# cannot survive a `.cmd` forwarder's `%*` intact on Windows: cmd.exe strips
# the payload's double quotes during its OWN command-line parse, before the
# launcher body or Python ever runs, and the CLI then rejects a payload that
# was well-formed when sent. Shape W (the `.cmd` sibling through the call
# operator) is the rung `resolve-coordinator-bin.md` mandates on a Windows
# host, so without recovery the documented invocation shape and the
# JSON-argument surface are mutually exclusive there
# (cross-repo/inbox/2026-08-20-coordinator-content-repo-em-cmd-forwarder-eats-json-and-two-
# smaller-seams.md, item 1).
#
# Narrow and named on purpose, mirroring `gen-launcher-shim.py`'s own
# `_RAW_CMDLINE_ENTRYPOINTS` discipline: enrolment costs every invocation a
# capture file, so a target earns a row only when a quote-bearing argument is
# genuinely reachable in normal use. The three sets are kept in sync by
# convention -- this one, `gen-launcher-shim.py::_RAW_CMDLINE_ENTRYPOINTS`,
# and `coordinator_core/install/substrate.py::_RAW_CMDLINE_TARGETS` -- and
# `test_raw_cmdline_json_payload_enrolment.py` fails if they drift.
#: The JSON-valued flags recovered from the raw command line. Both spellings
#: of the inline form are listed because `--decisions` is the flag every
#: current parse site names; the `-file` sibling carries a PATH, which is
#: quote-and-space-free by construction and never needed recovery.
_JSON_PAYLOAD_FLAGS = ("--decisions",)

_JSON_PAYLOAD_TARGETS = frozenset(
    {
        "backlog-grind-assemble",
        "baton-assemble",
        "consolidate-assemble",
        "merge-assemble",
        "pickup-assemble",
        "workday-complete-assemble",
        "workstream-complete-assemble",
    }
)


def _recover_json_payload_argv(name: str, argv: List[str]) -> List[str]:
    """Returns `argv` with a `.cmd`-mangled JSON payload restored from the
    raw invoking command line, or `argv` unchanged when recovery does not
    apply or cannot be vouched for.

    Never raises and never refuses. `recover_windows_argv` raises
    `UnsoundRawCmdlineTransport` for a transport whose capture it cannot
    vouch for (git-bash/MSYS, `subprocess.run([...])` list-form) -- the
    consumers that REFUSE on it are low-traffic, agent-typed CLIs where a
    corrupt argument silently discharges nothing. These ceremony CLIs are
    not that shape: they are called by tests and by in-repo `subprocess`
    callers on the very transports that classify as unsound, and those
    callers pass argv that was never mangled in the first place. Turning
    that into a fleet-wide refusal would break working invocations to
    protect a payload most of them do not carry.

    So the posture here is recover-or-fall-through: PowerShell's
    outer-quoted `cmd /c ""<exe>" <args>"` form -- the documented Shape W
    rung, and the shape the reported break arrived on -- recovers and the
    inline payload now parses. Every other transport keeps exactly today's
    behaviour, and a payload that really did lose its quotes still fails at
    the JSON parse, where `ceremony_common.json_payload_flag` names the
    forwarder as the likely vehicle and points at `--decisions-file`.

    Negative-spec:
        - Does NOT apply to targets outside `_JSON_PAYLOAD_TARGETS`. An
          unenrolled target's launcher emits no capture file at all, so the
          call would be a no-op anyway; keeping the set test explicit means
          the enrolment sets stay the single place the question is answered.
        - Does NOT parse, validate, or inspect the payload. Whether the
          recovered token is well-formed JSON stays entirely the parse
          site's business.
    """
    if name not in _JSON_PAYLOAD_TARGETS:
        return argv
    try:
        _lib = str(Path(__file__).resolve().parent)
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        from raw_cmdline_recovery import (  # noqa: PLC0415 -- optional, Windows-only
            recover_json_flag_argv,
        )
    except Exception:  # noqa: BLE001 -- module absent/unimportable: no recovery
        return argv

    try:
        return list(recover_json_flag_argv(list(argv), f"{name}.cmd", _JSON_PAYLOAD_FLAGS))
    except Exception:  # noqa: BLE001 -- recovery must never break an invocation
        return argv


class UnknownTargetError(LookupError):
    """Raised when a requested subcommand name is not one of ASSEMBLE_TARGETS."""


def _record_invocation(name: str) -> None:
    try:
        # ORDERING IS LOAD-BEARING, and getting it wrong was a real defect
        # (found 2026-08-16 during workstream-complete review, introduced by
        # this hook). `coordinator_core.ops.<anything>` triggers that
        # package's `_eager_import_all` over ~206 op modules, and several of
        # them import the top-level `coordinator` package. If this hook runs
        # BEFORE `_import_engine_module` puts the engine root on `sys.path`,
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
    lib_dir = str(BIN_DIR / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    from cc_invoke import _resolve_engine_root  # noqa: E402

    return _resolve_engine_root


def _import_engine_module(dotted: str):
    resolve_claude_klabauter_root = _cc_invoke_resolve_claude_klabauter_root()
    claude_klabauter_root = resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    return importlib.import_module(dotted)


def _simple_entry(name: str, dotted: str) -> Callable[[List[str]], int]:

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


#: Mirrors `apply_base.APPLY_EXIT_PARTIAL_MUTATION` (4) without importing
#: `coordinator_core.contract.apply_base` at cold-path module scope -- this
#: module's other engine-mapped entries already avoid importing their
#: target's dependency graph until an actual invocation reaches them
#: (`_import_engine_module`), and this one value is cheap to duplicate
#: rather than pay for.
_APPLY_EXIT_PARTIAL_MUTATION = 4


def _merge_assemble_is_method_not_found(exc: BaseException) -> bool:
    """True when `exc` is `cc_invoke`'s generic `RuntimeError` wrapping a
    JSON-RPC `-32601` (Method not found) error envelope.

    No typed signal exists for this (`cc_invoke.py` converts the envelope's
    `error` dict to a bare `RuntimeError` whose message embeds `code=-32601`,
    with no exception subclass and no code field — verified at source,
    `coordinator/bin/lib/cc_invoke.py` lines ~1808-1811 and ~1991-1994). This
    predicate is the ONE named home for that fragility, mirroring the
    identical precedent in `coordinator/bin/coordinator-safe-commit.py ::
    _op_is_unregistered` (`"-32601" in str(exc) or "Method not found" in
    str(exc)`), so a future engine-message rewording is one place to fix,
    not a per-caller grep.

    Narrow on purpose: method-not-found is the ONE dispatch failure that
    says nothing ran (the seam answered, no handler matched), so falling
    back to the cold path is safe for both merge-assemble verbs. Every
    other `RuntimeError` out of `cc_invoke.route` — including a timeout,
    which `is_timeout_error` already discriminates for callers that need
    it — must NOT match this predicate, or a live-but-broken engine gets
    silently masked instead of surfaced (DR-215 anti-scope, `route`'s own
    docstring)."""
    text = str(exc)
    return "-32601" in text or "Method not found" in text


def _merge_assemble_checked_repo_root() -> Optional[str]:
    """Resolve the repo root `cc_invoke.route` dispatches against, via the
    same checked resolver `coordinator/bin/lib/op_trampoline.py :: run` uses
    for every other warm-routed CLI in this directory — never `Path.cwd()`/
    `Path(__file__)` directly. A MISMATCH verdict is warned to stderr and
    the resolved root used anyway (DR-277 reader convention); UNRESOLVED
    (`None`) is returned as-is and left to the caller."""
    lib_dir = str(BIN_DIR / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    from repo_identity import resolve_checked_repo_root  # noqa: PLC0415

    repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if repo_root is not None and isinstance(verdict, dict) and verdict.get("verdict") == "MISMATCH":
        print(verdict.get("message", ""), file=sys.stderr)
    return repo_root


def _merge_assemble_cold_call(op: str, params: dict) -> dict:
    if op == "merge_assemble.apply":
        apply_mod = _import_engine_module("coordinator_core.merge_assemble.apply")
        exit_code, report = apply_mod.apply(
            session_id=params.get("session_id"),
            repo_root=None,
            decisions=params.get("decisions"),
            force=bool(params.get("force", False)),
            tag_prefix=params.get("tag_prefix", "v"),
        )
        return {"exit_code": exit_code, "report": report}
    raise ValueError(f"_merge_assemble_cold_call: unknown op {op!r}")


def _merge_assemble_dispatch(op: str, params: dict, print_fn, result_key: str, *, is_apply: bool) -> int:
    resolve_claude_klabauter_root = _cc_invoke_resolve_claude_klabauter_root()
    claude_klabauter_root = resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    lib_dir = str(BIN_DIR / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    import cc_invoke  # noqa: PLC0415

    repo_root = _merge_assemble_checked_repo_root()

    served_cold = False

    def _legacy_fn():
        nonlocal served_cold
        served_cold = True
        return _merge_assemble_cold_call(op, params)

    try:
        result = cc_invoke.route(op, params, repo_root, _legacy_fn)
    except RuntimeError as exc:
        if not served_cold and _merge_assemble_is_method_not_found(exc):
            result = _merge_assemble_cold_call(op, params)
            served_cold = True
        elif is_apply:
            # Post-dispatch (or undiscriminable — fail closed per AC6):
            # never retry cold, an apply directive may already have landed.
            #
            # `is_timeout_error` sharpens the OPERATOR MESSAGE only; it must not
            # gate the routing above. AC6 fails closed on every undiscriminable
            # residual, so a timeout and an unrecognized RuntimeError take the
            # same branch by design. What differs is what we can honestly tell
            # the operator: a timeout carries cc_invoke's own documented
            # guarantee that the engine was NOT stopped, so the op may well have
            # landed in full, whereas an unclassified failure leaves even that
            # unknown. Routing them identically while reporting them identically
            # would discard the one discriminator the transport actually exposes.
            if cc_invoke.is_timeout_error(exc):
                detail = (
                    "the op ran past its budget; the engine was NOT stopped, so "
                    "this apply may have landed in full"
                )
            else:
                detail = (
                    "the failure could not be classified as pre- or "
                    "post-dispatch, so it is treated as post-dispatch"
                )
            print(
                f"{op}: apply transport failure after dispatch — {detail}. The "
                f"operator may be in a partial-mutation state "
                f"({_APPLY_EXIT_PARTIAL_MUTATION}); no cold retry: {exc}",
                file=sys.stderr,
            )
            return _APPLY_EXIT_PARTIAL_MUTATION
        else:
            print(f"{op}: transport failure: {exc}", file=sys.stderr)
            return _TRANSPORT_FAIL

    print(f"{op}: path={'cold' if served_cold else 'warm'}", file=sys.stderr)

    if not isinstance(result, dict):
        print(f"{op}: unexpected result shape {type(result).__name__}", file=sys.stderr)
        return _TRANSPORT_FAIL

    exit_code_raw = result.get("exit_code")
    exit_code_int: Optional[int] = None
    exit_code_castable = False
    if exit_code_raw is not None:
        try:
            exit_code_int = int(exit_code_raw)
            exit_code_castable = True
        except (TypeError, ValueError):
            exit_code_castable = False

    if exit_code_castable and exit_code_int != 0:
        print_fn(result.get(result_key))
        return exit_code_int

    refusal = cc_invoke.mutation_refusal_message(op, result)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return _TRANSPORT_FAIL

    print_fn(result.get(result_key))
    return exit_code_int if exit_code_castable else 0


def _native_route_entry(name: str, dotted: str) -> Callable[[List[str]], int]:
    legacy_entry = _simple_entry(name, dotted)

    def _entry(argv: List[str]) -> int:
        # NEGATIVE SPEC: served side runs the implementation; routing here
        # again would re-enter this same shim through the door (this `main`
        # IS what `invoke.from_argv` serves) -- unbounded self-recursion, cut
        # only by the mutation read deadline. The pool worker declares its
        # route (`server._worker_process_init`); a COLD-served
        # `invoke.from_argv` declares none, so `_run_entrypoint` marks the
        # served span itself (`SERVED_ENTRYPOINT_ENV`) -- without it each cold
        # rung spawns the next, forever. The caller side, undeclared, still
        # routes exactly as before.
        if (
            os.environ.get("COORDINATOR_EXECUTION_ROUTE") == "warm_server"
            or os.environ.get("COORDINATOR_SERVED_ENTRYPOINT")
        ):
            return legacy_entry(list(argv))

        lib_dir = str(BIN_DIR / "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        import cc_invoke  # noqa: PLC0415

        repo_root = _merge_assemble_checked_repo_root()
        params = {"argv": list(argv), "cwd": str(Path.cwd()), "entrypoint": name}

        result = cc_invoke.route(
            "invoke.from_argv", params, repo_root, lambda: legacy_entry(list(argv))
        )

        if isinstance(result, dict):
            stdout_text = result.get("stdout", "")
            stderr_text = result.get("stderr", "")
            if stdout_text:
                sys.stdout.write(stdout_text)
            if stderr_text:
                sys.stderr.write(stderr_text)
            exit_code = result.get("exit_code")
            return exit_code if isinstance(exit_code, int) else 1
        return int(result)

    return _entry


_merge_assemble_legacy_entry = _simple_entry("merge-assemble", "coordinator_core.merge_assemble")


def _merge_assemble_entry(argv: List[str]) -> int:
    """Warm-routed replacement for `_simple_entry("merge-assemble", ...)`
    (AC1-AC9). Parse/print stay C1's `coordinator_core.merge_assemble.cli`
    leaf functions; only the compute step between them now goes through
    `cc_invoke.route` with a cold fallback, per `_merge_assemble_dispatch`.

    Usage-error handling (missing/unknown subcommand, `--help`, an argv
    parse failure) is reproduced verbatim from the pre-change `main`/
    `main_apply` bodies — including `main_apply`'s own distinct usage exit
    code (`APPLY_EXIT_TRANSPORT_FAIL` == 3, not `main`'s `EXIT_USAGE` == 2)
    — since none of that is a routing decision."""
    prog = "merge-assemble"

    def _usage_top() -> int:
        print(
            f"usage: {prog} apply [--session-id <id>] [--force] [--decisions <json>]",
            file=sys.stderr,
        )
        return _USAGE_FAIL

    def _usage_apply() -> int:
        print(
            f"usage: {prog} apply [--session-id <id>] [--force] "
            "[--decisions <json> | --decisions-file <path>] [--tag-prefix <prefix>]",
            file=sys.stderr,
        )
        return _TRANSPORT_FAIL

    if not argv:
        return _usage_top()

    if argv[0] in ("--help", "-h"):
        print(f"usage: {prog} apply [--session-id <id>] [--force] [--decisions <json>]")
        return 0

    subcmd, rest = argv[0], argv[1:]

    if subcmd == "brief":
        print(
            f"{prog}: 'brief' was removed (K-114) — the compute step is no "
            "longer a standalone verb. Use 'apply', which recomputes the "
            "same brief in-process.",
            file=sys.stderr,
        )
        return _usage_top()

    if subcmd != "apply":
        print(f"{prog}: unknown subcommand {subcmd!r}", file=sys.stderr)
        return _usage_top()

    try:
        cli_mod = _import_engine_module("coordinator_core.merge_assemble.cli")
    except (RuntimeError, ImportError):
        # Seam-absent, PRE-DISPATCH: either CLAUDE_KLABAUTER_ROOT itself would not
        # resolve, or it resolved to a root that has not yet been published
        # with C1's `coordinator_core.merge_assemble.cli` split (observed:
        # the resolved root can legitimately be a sibling publish tree that
        # still only carries the pre-plan `coordinator_core.merge_assemble`
        # package). Nothing has parsed argv or dispatched anything yet, so
        # per AC6 this falls back cold — to the exact pre-warm-routing
        # `_simple_entry` shape, which targets the package itself (not
        # `.cli`) and always existed there.
        return _merge_assemble_legacy_entry(argv)

    try:
        params = cli_mod.parse_apply_argv(rest)
    except cli_mod.UsageError as exc:
        if exc.message is not None:
            print(exc.message, file=sys.stderr)
        return _usage_apply()
    return _merge_assemble_dispatch(
        "merge_assemble.apply", params, cli_mod.print_apply_result, "report", is_apply=True
    )


def _backlog_grind_assemble_entry(argv: List[str]) -> int:
    usage_text = (
        "usage: backlog-grind-assemble brief|mint-run-id|apply|drop|grind-row <cadence|verb> [...]"
    )

    def _usage() -> int:
        print(usage_text, file=sys.stderr)
        return _USAGE_FAIL

    if not argv:
        return _usage()
    if argv[0] in ("--help", "-h"):
        print(usage_text)
        return 0

    subcommand, rest = argv[0], argv[1:]
    if subcommand not in ("brief", "mint-run-id", "apply", "drop", "grind-row"):
        return _usage()

    try:
        resolve_claude_klabauter_root = _cc_invoke_resolve_claude_klabauter_root()
        claude_klabauter_root = resolve_claude_klabauter_root()
        if claude_klabauter_root not in sys.path:
            sys.path.insert(0, claude_klabauter_root)
        import coordinator_core.backlog_grind_assemble as brief_mod
        import coordinator_core.backlog_grind_assemble.apply as apply_mod
        import coordinator_core.backlog_grind_assemble.grind_rows as grind_rows_mod
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
    if subcommand == "grind-row":
        from coordinator_core.cli_entry import recording_declared_writes

        with recording_declared_writes():
            return grind_rows_mod.main(rest)
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
# BY_PATH_TARGETS. Derived by reading each of the 14 bin/*.py files' actual
# imports/calls (not guessed from the entry-point name) — see the module
# docstring above and each target's own comment for the file it was derived
# from.
_ENGINE_ENTRIES: dict[str, Callable[[List[str]], int]] = {
    "backlog-grind-assemble": _backlog_grind_assemble_entry,
    "baton-assemble": _native_route_entry("baton-assemble", "coordinator_core.baton_assemble"),
    "consolidate-assemble": _simple_entry("consolidate-assemble", "coordinator_core.consolidate_assemble"),
    "merge-assemble": _merge_assemble_entry,
    "orient-assemble": _simple_entry("orient-assemble", "coordinator_core.orient_assemble"),
    "pickup-assemble": _native_route_entry("pickup-assemble", "coordinator_core.pickup_brief"),
    "plan-assemble": _simple_entry("plan-assemble", "coordinator_core.plan_assemble"),
    "quick-wrap-assemble": _simple_entry("quick-wrap-assemble", "coordinator_core.quick_wrap_assemble"),
    "review-assemble": _simple_entry("review-assemble", "coordinator_core.review_assemble"),
    "sizing-assemble": _simple_entry("sizing-assemble", "coordinator_core.sizing_assemble"),
    "staff-session-assemble": _simple_entry("staff-session-assemble", "coordinator_core.staff_session_assemble"),
    "workday-complete-assemble": _workday_complete_assemble_entry,
    "workstream-complete-assemble": _native_route_entry("workstream-complete-assemble", "coordinator_core.workstream_complete"),
}


def _load_module(name: str, path: Path):
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
# 59 entry points, one dispatcher (coordinator-gate.py). Same shim mechanism
# as ASSEMBLE_TARGETS above (in-process, no subprocess), but this family is
# far less uniform than the 14 `-assemble` entries: at least four distinct
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
    "verify-content-root-seam-sync",
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

assert len(GATE_TARGETS) == 59, f"expected 59 gate targets, counted {len(GATE_TARGETS)}"

# The corrected denominator for a shim-usage census (chunk C10 of
# docs/plans/2026-08-21-the-cli-bootstrap-tax-dies-at-the-interpreter-floor.md).
#
# A naive cross-reference of "how many of the 434 shipping CLIs has
# `record_invocation` ever seen fire" reads as 20 -- the count of bin/*.py
# files that actually `import entry_point_shim` (the 13 converted
# `-assemble` shims, the 5 converted GATE_ENGINE_ENTRIES shims, and the two
# batch dispatchers `coordinator-assemble.py`/`coordinator-gate.py`). That
# number answers "how many FILES route through this module", not "how many
# NAMES this module's census can account for" -- `run_target` and
# `run_gate_target` both call `_record_invocation(name)` unconditionally,
# for every name in ASSEMBLE_TARGETS/GATE_TARGETS, regardless of whether
# that name's own standalone bin/<name>.py has been converted to a shim.
# A GATE_TARGETS member still resolved BY PATH (`GATE_BY_PATH_TARGETS`)
# still gets recorded the moment it is reached through
# `coordinator-gate.py`'s batched dispatch -- only a DIRECT invocation of
# that name's own untouched .py file (bypassing both dispatchers) escapes
# the census.
#
# So the true instrumented surface is this union: every name this module's
# two dispatch tables know how to route AT ALL, whether by engine-callable
# or by-path. Reading "417 of 434 never invoked" off the 20-file count
# is FALSE -- it conflates 414 UNINSTRUMENTED names (no evidence either
# way) with genuinely dead ones. `ALL_TARGETS` is the corrected 74-name
# enumeration a census should read invocation evidence against; the
# remaining 434-74 names are not covered by this module at all and stay
# correctly "uninstrumented", not "unused".
ALL_TARGETS = tuple(ASSEMBLE_TARGETS) + tuple(GATE_TARGETS)


def _run_op_main_entry(name: str, dotted: str, fail_exit: int = 1) -> Callable[[List[str]], int]:

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
    """Run one of the 59 GATE_TARGETS entry points in-process and return its
    exit code. `argv` excludes the subcommand name itself.

    Unlike `run_target` above (whose 14 ASSEMBLE_TARGETS members' `main`
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
        # sys.argv asymmetry, audited empirically.
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


_HELP_FLAGS = ("--help", "-h")


def _help_requested(argv: List[str]) -> bool:
    """True if `--help`/`-h` appears ANYWHERE in argv, including after a
    subcommand token (`baton-assemble brief --help`). Position is
    deliberately not special-cased: a partially-typed command is exactly
    when the gesture is reached for.

    Spec backlink: docs/plans/2026-09-02-the-loader-fires-the-assembly-not-
    the-em.md, chunk C1, NEGATIVE SPEC.
    """
    return any(a in _HELP_FLAGS for a in argv)


def _synthesize_usage(name: str) -> str:
    return f"usage: {name} [--help]\n"


def _usage_lines(text: str) -> str:
    """Returns only the usage-bearing lines of `text` (case-insensitive
    substring "usage"), joined with a trailing newline, or "" if none.

    Exists because two engine-mapped targets (`plan-assemble`, `workday-
    complete-assemble`) print their real usage line to stderr ALONGSIDE a
    genuine parse-error line (`"plan-assemble: unrecognized argument
    '--help'"`) — that error line is a true statement about how the
    target's own hand-rolled parser sees an unrecognized `--help` token,
    but it is not something a successful help gesture should surface. This
    filters line-by-line rather than discarding stderr wholesale, so the
    one line that IS real usage is kept and the error line beside it is
    not.
    """
    lines = [ln for ln in text.splitlines() if "usage" in ln.lower()]
    return ("\n".join(lines) + "\n") if lines else ""


def _render_help(name: str) -> str:
    """Returns the usage text to print for `name`'s `--help` gesture,
    without ever running the target's op.

    `name in BY_PATH_TARGETS`: the sole member's `main()` takes no argv
    (`del argv` at workday-start-inbox-blitz-assemble.py:519) and always
    runs its full body regardless of what it is called with, so it is
    NEVER invoked here — a synthesized line is the only safe answer.

    Every other name: `_ENGINE_ENTRIES[name]` is called with `["--help"]`
    only, both stdout and stderr redirected to buffers. The per-target
    safety basis for that call splits into two shapes, each verified by
    reading that target's own `main` (or delegating entry function) rather
    than assumed by pattern-matching the rest:

    - Most targets handle `--help`/`-h` as an EXPLICIT, first-checked
      branch in their own dispatch (`main`, or in the two engine-mapped
      cases `_backlog_grind_assemble_entry`/`_merge_assemble_entry` in this
      module), returning before any op-reaching code runs — not argparse's
      `-h` action; every one of these is a hand-rolled positional/flag
      dispatch.
    - A small remainder (`plan-assemble`, `workday-complete-assemble`) has
      NO explicit `--help` branch and falls through to its existing
      usage/error path instead: `plan-assemble`'s `_dispatch_brief` raises
      a route-usage error inside its own route-parsing before `brief()`'s
      compute step is ever reached; `workday-complete-assemble`'s
      `_workday_complete_assemble_entry` (this module) checks the
      subcommand is one of `("brief", "apply")` before either sub-`main`
      import, so an unrecognized `--help` token returns at that guard. For
      both, the captured text is filtered through `_usage_lines` to keep
      only the real usage line and drop the parse-error line beside it
      (see that function's docstring) — this is what turns a target with
      no `--help` surface of its own into a delegated (not synthesized)
      render, since the usage text it already has is real and worth
      keeping.

    The full per-target partition (which targets fall in each shape, and
    the exact real-usage substring each renders) is asserted by the
    parametrized suite in `coordinator/bin/lib/tests/test_assemble_help_
    contract.py` — `test_delegated_targets_render_their_own_real_usage`,
    `test_only_the_by_path_target_has_a_run_target_bypassing_main_entry`,
    and `test_synthesis_is_used_only_for_the_by_path_target` (the by-path
    target is the only one where a line is synthesized rather than
    delegated) — read that suite for the live, per-target register rather
    than this docstring.
    """
    if name in BY_PATH_TARGETS:
        return _synthesize_usage(name)

    entry = _ENGINE_ENTRIES[name]
    out_buf, err_buf = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            entry(["--help"])
    except SystemExit:
        pass
    except Exception:  # noqa: BLE001 -- a target's own --help handling
        pass

    stdout_text = out_buf.getvalue()
    if stdout_text.strip() and "usage" in stdout_text.lower():
        return stdout_text

    stderr_usage = _usage_lines(err_buf.getvalue())
    if stderr_usage:
        return stderr_usage

    return _synthesize_usage(name)


def run_target(name: str, argv: List[str]) -> int:
    """Run the named `-assemble` entry point in-process and return its exit
    code. `argv` excludes the subcommand name itself (mirrors `sys.argv[1:]`
    for direct invocation of the target `.py`).

    `--help`/`-h` is intercepted here, at the top, before any of the
    dispatch machinery below runs: before `_record_invocation`, before
    `_recover_json_payload_argv`, and before either resolution branch.
    Usage is printed to stdout and 0 is returned; the target's op is never
    reached, and a help gesture is never counted as an op invocation for
    C9's deprecation-window census. See `_render_help` for how the usage
    text is sourced. Spec backlink: docs/plans/2026-09-02-the-loader-fires-
    the-assembly-not-the-em.md, chunk C1.

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

    if _help_requested(argv):
        sys.stdout.write(_render_help(name))
        return 0

    _record_invocation(name)

    argv = _recover_json_payload_argv(name, list(argv))

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

    # sys.argv asymmetry, audited empirically. This
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
