"""SessionStart sync fan-in dispatcher -- the SessionStart registrations that
emit boot context, one interpreter, source-gated.

Folds `session-start-repin-cloud-engine-root.py`,
`session-start-watch-presence.py`, `session-start-cloud-focus.py`,
`project-orientation.py`, `guard-settings-integrity.py`,
`guard-foreign-platform-paths.py`, `session-start-write-bump-anchor.py`,
`sessionstart-bin-drift-refresh.py`, `day-branch-assert.py`,
`session-start-announce-job-mode.py`,
`session-start-governed-surface-drift.py` and
`guard-hook-generation-self-probe.py` into ONE `python3` process,
registered on `startup|resume|clear|compact|fork`, following the registry +
dynamic-import pattern `stop-dispatch.py` / `preuse-agent-dispatch.py`
already ship.

HEAD LEGS. The harness shows only the first ~2,048 characters of a hook's
stdout; a payload that starts past that window never reaches context. The
first three REGISTRY rows (`HEAD_LEGS`) own stream offset 0: the repin leg
(zero stdout, always first), then watch-presence and cloud-focus. A head leg
can only be pushed out of the window by the head legs ahead of it, and
`tests/test_sessionstart_dispatch_head_legs.py`'s per-leg ceilings plus head total keep
that inside `PREVIEW_WINDOW_CHARS`, so growth fails a test instead of
truncating silently.

`assert-em-role.py` is the one SessionStart leg that stays its OWN top-level
registration. Its composed payload is budgeted at 1,944 of the 2,048-character
window, so no stream it shares can keep it whole; a separate registration gives
it its own stdout stream and its own preview window.

ENVELOPE UNWRAP. watch-presence and cloud-focus emit a JSON
`hookSpecificOutput` envelope; every other leg writes plain text. This stream
is plain text, so a leg whose captured stdout parses as exactly one JSON
object carrying `hookSpecificOutput.additionalContext` (a string) is written
as that text plus a newline. Any other stdout passes through byte-exact.

ENGINE PURGE. The repin leg re-points the engine-root symlink. Once it
returns, this dispatcher drops every `sys.modules` entry named
`coordinator_core` or `coordinator_core.*` and restores `sys.path` to its
pre-leg snapshot, so the next leg resolves and imports the engine fresh
through the repointed symlink rather than mixing pre- and post-repin modules.

NOT folded, deliberately:
  - `session-start-register-coordinator-content-repo-root.py` and `session-start-repair-
    prepare-commit-msg-hook.py` -- both `async: true` (their whole value is a
    side-effect write with no context-bound stdout, kept off boot-latency).
    Folding an async hook into a SYNC dispatcher process would force it to
    block session start -- see `sessionstart-async-dispatch.py`, which folds
    those instead, preserving their async-ness exactly.

SOURCE-GATING, NOT MATCHER-NARROWING. The folded legs span several matcher
sets, so this dispatcher registers on their union
(`startup|resume|clear|compact|fork`). Narrowing
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
resolves `CLAUDE_CONFIG_DIR` / the engine root independently via its
own `_resolve_claude_klabauter_root()` -- a different, guard-specific resolution this
dispatcher does not attempt to unify (out of scope; see the settings.json
triple-read note below).

SETTINGS.JSON TRIPLE-READ (named, not fixed here). Three of these guards
(`guard-settings-integrity.py`, `guard-foreign-platform-paths.py`,
`guard-hook-generation-self-probe.py`) each independently resolve
`CLAUDE_CONFIG_DIR`/`settings.json` and call a THIN plugin-side stub that
hands off to an engine-plane function, which does its OWN independent
file read. Folding these three into one process does not, by itself,
collapse that to one read: the read lives inside each engine function's
own body (`coordinator_core.ops.session.*`), an engine-plane surface this
repo holds no commit grant to edit without per-session PM assent
(`CLAUDE.md` § Place in the fleet). A shared read is possible only if
those three engine functions grew a parameter accepting pre-read settings
content -- an engine-plane change, not something this fold can do
unilaterally. Not fixed in this dispatch; flagged for the engine side.

`project-orientation.py` takes `argv` (it needs `--lightweight`, matching
its ONLY production invocation shape).

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
    """Computed once per SessionStart event."""

    def __init__(self, raw: str) -> None:
        self.raw = raw
        try:
            p = json.loads(raw) if raw else {}
            payload = p if isinstance(p, dict) else {}
        except Exception:
            payload = {}
        src = payload.get("source")
        self.source: str = src if isinstance(src, str) else ""
        sid = payload.get("session_id")
        self.session_id: str = sid if isinstance(sid, str) else ""
        cwd = payload.get("cwd")
        self.cwd: str = cwd if isinstance(cwd, str) else ""


@dataclass(frozen=True)
class StartGuard:
    module_key: str
    filename: str
    sources: FrozenSet[str]
    #: None -> invoke bare main(); a list -> invoke main(that_list) explicitly (never relies on
    #: this dispatcher's own sys.argv).
    argv: Optional[List[str]] = None


#: Emitted when a non-empty `source` matches no guard's set at all -- the harness-drift tell.
#: Skipping stays the behaviour; going quiet about it does not.
_UNMATCHED_SOURCE_BREADCRUMB = (
    "[sessionstart-dispatch] source={source!r} matches no guard in REGISTRY -- "
    "every guard skipped for this boot. If the harness added a source value, "
    "add it to the per-guard `sources` sets, not just the hooks.json matcher.\n"
)


REGISTRY: Tuple[StartGuard, ...] = (
    # HEAD LEGS -- see module docstring. Repin is leg 0 and must emit nothing.
    StartGuard("session_start_repin_cloud_engine_root",
               "session-start-repin-cloud-engine-root.py",
               frozenset({"startup", "resume", "clear", "compact", "fork"})),
    StartGuard("session_start_watch_presence", "session-start-watch-presence.py",
               frozenset({"startup", "resume", "clear", "compact", "fork"})),
    StartGuard("session_start_cloud_focus", "session-start-cloud-focus.py",
               frozenset({"startup"})),
    StartGuard("project_orientation", "project-orientation.py",
               frozenset({"startup", "clear", "compact"}), argv=["--lightweight"]),
    StartGuard("guard_settings_integrity", "guard-settings-integrity.py",
               frozenset({"startup", "clear", "compact"})),
    StartGuard("guard_foreign_platform_paths", "guard-foreign-platform-paths.py",
               frozenset({"startup", "clear", "compact"})),
    StartGuard("session_start_write_bump_anchor", "session-start-write-bump-anchor.py",
               frozenset({"startup", "resume", "clear", "compact", "fork"})),
    # `startup` only: what it watches changes when a template is edited, not when a session
    # compacts or clears, and its own daily stamp makes extra firings no-ops anyway.
    StartGuard("bin_drift_refresh", "sessionstart-bin-drift-refresh.py",
               frozenset({"startup"})),
    # `startup` ONLY, and this one is load-bearing rather than merely narrow:
    # this is the fan-in's one genuinely git-MUTATING leg (it cuts the day
    # branch when the tree sits on `main`, per the PM ruling of 2026-08-18).
    # `compact`, `resume` and `fork` all fire mid-execution, and a cut on
    # `compact` is the mid-execution mutation doctrine keeps out of bounds.
    # See the negative-spec in `day-branch-assert.py`; widening this set turns
    # `test_sessionstart_day_branch_assert_registered.py` red.
    StartGuard("day_branch_assert", "day-branch-assert.py",
               frozenset({"startup"})),
    # `startup` only: `job_mode` is a property of the environment a human launched the session in
    # -- it cannot change mid-session, so announcing again on resume/clear/compact/fork would
    # repeat a fact unchanged since boot.
    StartGuard("job_mode_announce", "session-start-announce-job-mode.py",
               frozenset({"startup"})),
    # Every source: the boot payload is re-read on each of them, and the check is one in-process
    # tree walk. Silent unless uncommitted governed-surface text fails admission.
    StartGuard("governed_surface_drift", "session-start-governed-surface-drift.py",
               frozenset({"startup", "resume", "clear", "compact", "fork"})),
    # LAST, deliberately -- see module docstring "INCREMENTAL FLUSH".
    StartGuard("guard_hook_generation_self_probe", "guard-hook-generation-self-probe.py",
               frozenset({"startup", "clear", "compact"})),
)


#: The legs owning stream offset 0; must equal the first three REGISTRY keys.
HEAD_LEGS: Tuple[str, ...] = (
    "session_start_repin_cloud_engine_root",
    "session_start_watch_presence",
    "session_start_cloud_focus",
)

_REPIN_KEY = HEAD_LEGS[0]


def _unwrap_envelope(out: bytes) -> bytes:
    """A leg's stdout that is exactly one JSON object carrying
    `hookSpecificOutput.additionalContext` (a string) becomes that text plus a newline;
    anything else is returned byte-exact."""
    try:
        obj = json.loads(out.decode("utf-8"))
        text = obj["hookSpecificOutput"]["additionalContext"]
    except Exception:
        return out
    if not isinstance(text, str):
        return out
    return (text + "\n").encode("utf-8")


def _purge_engine(path_snapshot: List[str]) -> None:
    """Invalidates what a repointed engine root made stale: every `coordinator_core` module and
    any `sys.path` entry the repin leg added."""
    for name in [n for n in sys.modules
                 if n == "coordinator_core" or n.startswith("coordinator_core.")]:
        del sys.modules[name]
    sys.path[:] = path_snapshot


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
    """Some folded guards emit through `sys.stderr.buffer.write()`, which a plain StringIO has no
    attribute for. Both channels land in one ordered `io.BytesIO` -- `write(str)` encodes into it,
    `.buffer.write(bytes)` writes unmodified -- so `combined()`/`combined_bytes()` are
    order-preserving and byte-exact rather than concatenating two separately-accumulated
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


def _snapshot_surfaces(ctx: Ctx) -> None:
    """Records load-time surfaces for `bin/needs-restart.py`; silent, fail-open."""
    try:
        import session_surface_snapshot
        session_surface_snapshot.write_snapshot(ctx.session_id, ctx.source, ctx.cwd or None)
    except BaseException:
        pass


def main() -> int:
    raw = sys.stdin.read()
    ctx = Ctx(raw)

    skipped: List[str] = []

    _snapshot_surfaces(ctx)

    if ctx.source and not any(ctx.source in g.sources for g in REGISTRY):
        sys.__stderr__.write(_UNMATCHED_SOURCE_BREADCRUMB.format(source=ctx.source))
        sys.__stderr__.flush()

    for guard in REGISTRY:
        # An empty source runs every guard (fail-open on a missing signal); a non-empty one gates
        # to that guard's own set.
        if ctx.source and ctx.source not in guard.sources:
            continue
        try:
            mod = _import_guard(guard)
        except BaseException:
            skipped.append(guard.module_key + " (import)")
            continue
        path_snapshot = list(sys.path)
        try:
            rc, out, err = _invoke(getattr(mod, "main"), guard.argv, raw)
        except BaseException:
            skipped.append(guard.module_key)
            continue
        finally:
            if guard.module_key == _REPIN_KEY:
                _purge_engine(path_snapshot)
        out = _unwrap_envelope(out) if out else out
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
        # Exit code carries no signal for any guard here: every guard is banner-only except
        # `day_branch_assert`, which mutates git (cuts the day branch on main) but still reports
        # through the banner channel and is fail-open by design, so a nonzero exit from it never
        # signals a real failure to surface.
        del rc

    if skipped:
        sys.__stderr__.write(
            "[sessionstart-dispatch] guard(s) skipped (fail-open for those only): "
            + ", ".join(skipped) + "\n"
        )
        sys.__stderr__.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
