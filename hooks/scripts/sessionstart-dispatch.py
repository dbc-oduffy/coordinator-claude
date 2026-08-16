"""SessionStart sync fan-in dispatcher -- six hooks.json SessionStart
registrations, one interpreter, source-gated.

Folds `project-orientation.py`, `guard-settings-integrity.py`,
`guard-foreign-platform-paths.py`, `session-start-write-bump-anchor.py`,
`assert-em-role.py`, and `guard-hook-generation-self-probe.py` into ONE
`python3` process, registered on the UNION of their prior matchers
(`startup|resume|clear|compact|fork`), following the registry +
dynamic-import pattern `stop-dispatch.py` / `preuse-agent-dispatch.py`
already ship.

NOT folded, deliberately (see state/subagent-share/892113a3-8c0c-4fa8-bb68-
13c20ca4aad5/coordinatorexecutor-ef3486a7.md for the full reasoning):
  - `sweep-boot.py` -- explicit handoff instruction (state/handoffs/
    2026-08-16-untitled-6c1eb4ae.md § Next Steps 1): its 30s timeout must
    not hide behind a short one. Stays its own standalone registration.
  - `session-start-register-doe-claude-root.py` and `session-start-repair-
    prepare-commit-msg-hook.py` -- both registered `async: true` in the
    prior manifest (their whole value is a side-effect write with no
    context-bound stdout, DELIBERATELY kept off boot-latency). Folding an
    async hook into a SYNC dispatcher process would force it to block
    session start, a real behaviour change this fold does not make
    unilaterally -- see `sessionstart-async-dispatch.py`, which folds
    those two instead, preserving their async-ness exactly.

SOURCE-GATING, NOT MATCHER-NARROWING. Across all nine prior registrations,
matchers spanned FOUR distinct sets: `startup|clear|compact` (four of the
six folded HERE: project-orientation.py, guard-settings-integrity.py,
guard-foreign-platform-paths.py, guard-hook-generation-self-probe.py),
`startup|resume|clear|compact|fork` (the other two folded here:
session-start-write-bump-anchor.py, assert-em-role.py), `startup|compact`
(sweep-boot.py -- deliberately NOT folded, see above), and `startup` alone
(session-start-repair-prepare-commit-msg-hook.py -- folded into
sessionstart-async-dispatch.py instead, see above). This dispatcher folds
only the first two of those four sets -- the six guards in REGISTRY below --
registered on their union (`startup|resume|clear|compact|fork`). Narrowing
HERE, per guard, on the harness's own SessionStart payload `source` field
(confirmed present and enumerated exactly as
`startup|resume|clear|compact|fork` by the vendored docs,
`state/reference/anthropic-docs/claude-code/hooks.md` § SessionStart Input
fields -- not inferred from the matcher strings) reproduces each guard's
ORIGINAL firing set exactly, never wider. A guard whose `sources` frozenset
does not contain the payload's `source` is skipped entirely (not imported,
not invoked) for that boot. An ABSENT/empty `source` runs every guard --
fail-open on the classification, matching this repo's pervasive fail-open
posture rather than narrowing a firing set on a missing signal.

A NON-EMPTY but unrecognised `source` skips every guard, which is what the
pre-fold registrations did too: the harness's own matcher gate would not
have fired a hook enumerating `startup|resume|clear|compact|fork` against
an unknown source string either, so this is not a narrowing the fold
introduces. It is unreachable today -- the vendored docs enumerate exactly
those five values. It becomes reachable the moment a harness release adds a
sixth and someone widens the hooks.json matcher WITHOUT adding it to the
per-guard `sources` sets below, and the whole cohort would then go silent.
That is why `_UNMATCHED_SOURCE_BREADCRUMB` exists: the cohort still skips,
but it never skips quietly. Harness enumerations do drift -- assume this
fires eventually rather than that it is dead code.

INCREMENTAL FLUSH, NOT COLLECT-THEN-WRITE-ONCE (load-bearing, not a style
choice). `stop-dispatch.py` and `preuse-agent-dispatch.py` both accumulate
every guard's captured stdout/stderr and write once at the end. This
dispatcher CANNOT do that: `guard-hook-generation-self-probe.py`'s own
`main()` calls `os._exit(0)` on its documented ThreadPoolExecutor-timeout
fail-open path (its own module docstring: the only portable way to leave a
hung non-daemon worker behind without wedging the interpreter). `os._exit`
bypasses every `finally`/context-manager `__exit__` in this process,
including this dispatcher's own -- so if this dispatcher accumulated output
in memory and wrote it once at the end, self-probe's `os._exit(0)` would
silently discard every EARLIER guard's already-collected output along with
it, an outcome none of those guards' own fail-open contracts intend. This
dispatcher instead writes each guard's captured stdout/stderr to the REAL
`sys.__stdout__`/`sys.__stderr__` immediately after that guard returns,
before moving to the next -- so an `os._exit()` from any guard (self-probe
today; anything folded here in the future) only ever discards that guard's
OWN unflushed output, never a sibling's. `guard-hook-generation-self-probe`
is ALSO placed last in `REGISTRY` as belt-and-suspenders (nothing folded
here runs after it to lose), but the incremental-flush design is the actual
fix -- ordering alone would not protect a future re-ordering.

NO SHARED-ROOT INJECTION (unlike `stop-dispatch.py`'s `_git_root_walk`
share). None of these six guards resolve a plain git repo root; each
resolves `CLAUDE_CONFIG_DIR` / the claude-klabauter engine root independently via its
own `_resolve_claude_klabauter_root()` -- a different, guard-specific resolution this
dispatcher does not attempt to unify (out of scope; see the settings.json
triple-read note below).

SETTINGS.JSON TRIPLE-READ (named, not fixed here). Three of these guards
(`guard-settings-integrity.py`, `guard-foreign-platform-paths.py`,
`guard-hook-generation-self-probe.py`) each independently resolve
`CLAUDE_CONFIG_DIR`/`settings.json` and call a THIN DoE-side stub that
hands off to an engine-plane function, which does its OWN independent
file read. Folding these three into one process does not, by itself,
collapse that to one read: the read lives inside each engine function's
own body (`coordinator_core.ops.session.*`), an engine-plane surface this
repo holds no commit grant to edit without per-session PM assent
(`CLAUDE.md` § Place in the fleet). A shared read is possible only if
those three engine functions grew a parameter accepting pre-read settings
content -- an engine-plane change, not something this fold can do
unilaterally. Not fixed in this dispatch; flagged for the engine side.

`project-orientation.py` and `assert-em-role.py` both take `argv` (the
former needs `--lightweight`, matching its ONLY production invocation
shape; the latter's `main(argv)` ignores argv entirely per its own `del
argv` but is called with `[]` rather than relying on this dispatcher's own
`sys.argv`, which carries no such flags).

Spec: state/audits/2026-08-16-doe-spawn-totality-kill-list.md,
state/handoffs/2026-08-16-untitled-6c1eb4ae.md § Next Steps 1
Precedent this file follows: coordinator/hooks/scripts/stop-dispatch.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, FrozenSet, List, Optional, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


class Ctx:
    """Computed ONCE per SessionStart event."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        try:
            p = json.loads(raw) if raw else {}
            payload = p if isinstance(p, dict) else {}
        except Exception:
            payload = {}
        src = payload.get("source")
        self.source: str = src if isinstance(src, str) else ""


@dataclass(frozen=True)
class StartGuard:
    module_key: str
    filename: str
    sources: FrozenSet[str]
    # None -> invoke bare main(); a list -> invoke main(that_list) explicitly
    # (never relies on this dispatcher's own sys.argv).
    argv: Optional[List[str]] = None


#: Emitted when a non-empty `source` matches no guard's set at all -- the
#: harness-drift tell described in the module docstring. Skipping stays the
#: behaviour; going quiet about it does not.
_UNMATCHED_SOURCE_BREADCRUMB = (
    "[sessionstart-dispatch] source={source!r} matches no guard in REGISTRY -- "
    "every guard skipped for this boot. If the harness added a source value, "
    "add it to the per-guard `sources` sets, not just the hooks.json matcher.\n"
)


REGISTRY: Tuple[StartGuard, ...] = (
    StartGuard("project_orientation", "project-orientation.py",
               frozenset({"startup", "clear", "compact"}), argv=["--lightweight"]),
    StartGuard("guard_settings_integrity", "guard-settings-integrity.py",
               frozenset({"startup", "clear", "compact"})),
    StartGuard("guard_foreign_platform_paths", "guard-foreign-platform-paths.py",
               frozenset({"startup", "clear", "compact"})),
    StartGuard("session_start_write_bump_anchor", "session-start-write-bump-anchor.py",
               frozenset({"startup", "resume", "clear", "compact", "fork"})),
    StartGuard("assert_em_role", "assert-em-role.py",
               frozenset({"startup", "resume", "clear", "compact", "fork"}), argv=[]),
    # `startup` only: what it watches changes when someone edits a template, not
    # when a session compacts or clears, and its own daily stamp makes extra
    # firings no-ops anyway. Narrowest set that still reaches every machine.
    # Placed after the guards and before the self-probe: it emits at most one
    # informational line and gates nothing, so nothing here should wait on it.
    StartGuard("bin_drift_refresh", "sessionstart-bin-drift-refresh.py",
               frozenset({"startup"})),
    # LAST, deliberately -- see module docstring "INCREMENTAL FLUSH".
    StartGuard("guard_hook_generation_self_probe", "guard-hook-generation-self-probe.py",
               frozenset({"startup", "clear", "compact"})),
)


class _ByteSink:
    """Binary-mode facade for `_BufferedTextCapture.buffer`: writes bytes straight
    through, UNMODIFIED, into the SAME ordered `io.BytesIO` the text channel's
    `write(str)` encodes into -- no decode, no round-trip at capture time. Some
    folded guards emit through `sys.stdout.buffer.write()`/`sys.stderr.buffer.
    write()` specifically to bypass Windows text-mode CRLF translation
    (`project-orientation.py`'s `_w()` is the canonical example -- review finding
    B-F3; see `_stop_family_runner.py`'s `_ByteSink` docstring for the full
    rationale). `_invoke()` below returns RAW BYTES (`combined_bytes()`), and this
    dispatcher's own re-emission writes them through `sys.__stdout__.buffer`/
    `sys.__stderr__.buffer`, never the text wrapper, so that guarantee survives
    the round trip to the real process stdout/stderr."""

    def __init__(self, sink: "io.BytesIO") -> None:
        self._sink = sink

    def write(self, data: bytes) -> int:
        return self._sink.write(data)

    def flush(self) -> None:
        pass


class _BufferedTextCapture(io.StringIO):
    """Same shim `stop-dispatch.py`/`_stop_family_runner` use: some folded
    guards emit through `sys.stderr.buffer.write()`, which a plain StringIO
    has no attribute for. Both channels land in ONE ordered `io.BytesIO` --
    `write(str)` encodes into it, `.buffer.write(bytes)` writes into it
    unmodified -- so `combined()`/`combined_bytes()` are order-preserving AND
    byte-exact, rather than concatenating two separately-accumulated
    buffers."""

    def __init__(self) -> None:
        super().__init__()
        self._bytes = io.BytesIO()
        self.buffer = _ByteSink(self._bytes)

    def write(self, s: str) -> int:
        self._bytes.write(s.encode("utf-8"))
        return len(s)

    def combined(self) -> str:
        return self.combined_bytes().decode("utf-8", "replace")

    def combined_bytes(self) -> bytes:
        return self._bytes.getvalue()

    def getvalue(self) -> str:
        return self.combined()


def _import_guard(guard: StartGuard) -> Any:
    if guard.module_key in sys.modules:
        return sys.modules[guard.module_key]
    spec = importlib.util.spec_from_file_location(
        guard.module_key, str(_HOOKS_DIR / guard.filename)
    )
    if spec is None or spec.loader is None:
        raise ImportError(guard.filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[guard.module_key] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(guard.module_key, None)
        raise
    return mod


def _invoke(main_fn: Callable[..., int], argv: Optional[List[str]],
            stdin_text: str) -> Tuple[int, bytes, bytes]:
    """Returns RAW BYTES for both channels (`combined_bytes()`, not
    `combined()`) -- this dispatcher has no string-specific logic downstream
    (only truthiness checks before re-emission), so there is no reason to
    decode-then-re-encode a guard's captured output. `main()`'s INCREMENTAL
    FLUSH re-emits these bytes through `sys.__stdout__.buffer`/`sys.__stderr__
    .buffer` directly."""
    old_stdin = sys.stdin
    out_buf = _BufferedTextCapture()
    err_buf = _BufferedTextCapture()
    rc = 0
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        sys.stdin = io.StringIO(stdin_text)
        try:
            try:
                rc = main_fn(argv) if argv is not None else main_fn()
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 0
        finally:
            sys.stdin = old_stdin
    return (rc or 0), out_buf.combined_bytes(), err_buf.combined_bytes()


def main() -> int:
    raw = sys.stdin.read()
    ctx = Ctx(raw)

    skipped: List[str] = []

    if ctx.source and not any(ctx.source in g.sources for g in REGISTRY):
        sys.__stderr__.write(_UNMATCHED_SOURCE_BREADCRUMB.format(source=ctx.source))
        sys.__stderr__.flush()

    for guard in REGISTRY:
        # An empty source runs every guard (fail-open on a missing signal);
        # a non-empty one gates to that guard's own set. See the module
        # docstring on the unrecognised-source case and its breadcrumb.
        if ctx.source and ctx.source not in guard.sources:
            continue
        try:
            mod = _import_guard(guard)
        except BaseException:
            skipped.append(guard.module_key + " (import)")
            continue
        try:
            rc, out, err = _invoke(getattr(mod, "main"), guard.argv, raw)
        except BaseException:
            skipped.append(guard.module_key)
            continue
        # INCREMENTAL FLUSH -- see module docstring. Written to the real
        # stdout/stderr immediately, never accumulated for a final join.
        # `out`/`err` are raw bytes (`_invoke`'s `combined_bytes()`); written
        # through `.buffer`, never the text wrapper, so a guard's raw
        # sys.stdout.buffer.write()/sys.stderr.buffer.write() bytes (Windows
        # CRLF-translation fix) survive re-emission unmodified.
        if out:
            sys.__stdout__.buffer.write(out)
            sys.__stdout__.buffer.flush()
        if err:
            sys.__stderr__.buffer.write(err)
            sys.__stderr__.buffer.flush()
        del rc  # every folded guard here is banner-only; exit code carries no signal

    if skipped:
        sys.__stderr__.write(
            "[sessionstart-dispatch] guard(s) skipped (fail-open for those only): "
            + ", ".join(skipped) + "\n"
        )
        sys.__stderr__.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
