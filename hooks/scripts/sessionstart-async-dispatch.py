"""SessionStart async fan-in dispatcher -- two hooks.json SessionStart
registrations, one interpreter, source-gated. Registered `async: true`.

Folds `session-start-register-doe-claude-root.py` (previously matcher
`startup|resume|clear|compact|fork`) and `session-start-repair-prepare-
commit-msg-hook.py` (previously matcher `startup` only) into ONE `python3`
process, registered ASYNC on the union of their prior matchers
(`startup|resume|clear|compact|fork`). Both prior hooks were ALREADY async
in the manifest: neither produces context-bound stdout (their whole value
is a side-effect write -- a machine-local registry self-heal for the
former, a git `prepare-commit-msg` shim self-repair for the latter), so
this fold keeps both off first-token boot latency exactly as before.

WHY A SEPARATE FILE FROM `sessionstart-dispatch.py` (not one dispatcher for
all eight). `hooks.json` gives one `async` flag per command entry, not per
guard -- a single process cannot be registered both sync and async at once.
Folding an async-only guard into the sync dispatcher would force it
synchronous (added boot-blocking latency, a real behaviour change); folding
these two async guards into the sync dispatcher would have the same effect
in the other direction. Keeping the sync/async split as two files preserves
every guard's original blocking behaviour exactly -- a hosting change only,
never a policy change, matching this repo's fan-in precedent (`stop-
dispatch.py`, `preuse-agent-dispatch.py`).

SOURCE-GATING. `session-start-register-doe-claude-root.py`'s own matcher
equalled this dispatcher's matcher exactly (`startup|resume|clear|compact|
fork`), so it needs no gating -- it always runs. `session-start-repair-
prepare-commit-msg-hook.py` fired on `startup` only; gated here to
`source == "startup"` so it does not newly fire on resume/clear/compact/
fork. Same source rule as the sync dispatcher: an ABSENT/empty `source` runs
both guards rather than narrowing on a missing signal, while a NON-EMPTY but
unrecognised one skips both -- matching what the pre-fold registrations did,
since the harness matcher gate would not have fired them either. Unreachable
until a harness release adds a sixth source value and someone widens the
hooks.json matcher without widening the `sources` sets below; the cohort
would then go silent, so `_UNMATCHED_SOURCE_BREADCRUMB` makes that loud.
Read the sync dispatcher's docstring for the full reasoning.

Both guards are exception-isolated (`try/except BaseException`, stderr
skipped-list breadcrumb) though async stdout/stderr is discarded by the
harness -- kept for parity with every other dispatcher in this repo and
because a raised exception here still costs a bad exit code recorded by
whatever observes async hook completion, however little that is acted on
today.

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
from typing import Any, Callable, FrozenSet, List, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))


class Ctx:
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


#: Counterpart to the sync dispatcher's constant of the same name -- a
#: non-empty `source` matching no guard here skips the cohort, but loudly.
_UNMATCHED_SOURCE_BREADCRUMB = (
    "[sessionstart-async-dispatch] source={source!r} matches no guard in "
    "REGISTRY -- every guard skipped for this boot. If the harness added a "
    "source value, add it to the per-guard `sources` sets, not just the "
    "hooks.json matcher.\n"
)


REGISTRY: Tuple[StartGuard, ...] = (
    StartGuard("session_start_register_doe_claude_root",
               "session-start-register-doe-claude-root.py",
               frozenset({"startup", "resume", "clear", "compact", "fork"})),
    StartGuard("session_start_repair_prepare_commit_msg_hook",
               "session-start-repair-prepare-commit-msg-hook.py",
               frozenset({"startup"})),
    # LIFECYCLE OWNER FOR THE http FORWARDER, folded here rather than given its
    # own registration. Its module docstring said "NOT REGISTERED HERE ... the
    # DR's own Consequences section defers that wiring to a later chunk" -- this
    # is that chunk (C10). Left unregistered it was inert: the resident forwarder
    # on this box was started once by hand and nothing revived it.
    #
    # THIS IS LOAD-BEARING THE MOMENT ANY ENTRY IS type: "http". A dead forwarder
    # is not a deny, it is a CONNECTION REFUSAL at the harness -- a transport
    # error, which the http path FAILS OPEN on. Every guard behind that transport
    # then goes silently inert fleet-wide, which is a worse shape than the outage
    # 084654c8b reverted: an outage announces itself, a silent disarm does not.
    #
    # All five sources deliberately. The forwarder is a MACHINE-WIDE resident, so
    # the session that finds it missing is whichever one starts next -- there is
    # no reason that should be a `startup` in particular, and narrowing this set
    # would leave a box whose sessions all resume/fork with no forwarder at all.
    # Costs nothing on the overwhelmingly common path: the guard probe-binds,
    # loses to the incumbent, and treats losing as success (its own "ENSURE, NOT
    # SPAWN-BLINDLY" contract). Async and never-waits, per its own "NEVER WAIT".
    StartGuard("sessionstart_ensure_http_forwarder",
               "sessionstart-ensure-http-forwarder.py",
               frozenset({"startup", "resume", "clear", "compact", "fork"})),
)


class _ByteSink:
    """Binary-mode facade for `_BufferedTextCapture.buffer`: writes bytes straight
    through, UNMODIFIED, into the SAME ordered `io.BytesIO` the text channel's
    `write(str)` encodes into -- no decode, no round-trip at capture time. Some
    folded guards emit through `sys.stdout.buffer.write()`/`sys.stderr.buffer.
    write()` specifically to bypass Windows text-mode CRLF translation (see
    `_stop_family_runner.py`'s `_ByteSink` docstring for the full rationale).
    `_invoke()` below returns RAW BYTES (`combined_bytes()`), and this
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
    """Same shim `stop-dispatch.py`/`_stop_family_runner` use: some folded guards
    emit through `sys.stdout.buffer.write()`/`sys.stderr.buffer.write()`, which a
    plain StringIO has no attribute for. Both channels land in ONE ordered
    `io.BytesIO` -- `write(str)` encodes into it, `.buffer.write(bytes)` writes
    into it unmodified -- so `combined()`/`combined_bytes()` are order-preserving
    AND byte-exact, rather than concatenating two separately-accumulated
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


def _invoke(main_fn: Callable[[], int], stdin_text: str) -> Tuple[int, bytes, bytes]:
    """Returns RAW BYTES for both channels (`combined_bytes()`, not
    `combined()`) -- this dispatcher has no string-specific logic downstream
    (only truthiness checks before re-emission), so there is no reason to
    decode-then-re-encode a guard's captured output."""
    old_stdin = sys.stdin
    out_buf = _BufferedTextCapture()
    err_buf = _BufferedTextCapture()
    rc = 0
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        sys.stdin = io.StringIO(stdin_text)
        try:
            try:
                rc = main_fn()
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
        if ctx.source and ctx.source not in guard.sources:
            continue
        try:
            mod = _import_guard(guard)
        except BaseException:
            skipped.append(guard.module_key + " (import)")
            continue
        try:
            # Incremental flush, same rationale as sessionstart-dispatch.py:
            # a future guard folded here that ever exits via os._exit would
            # otherwise risk discarding an earlier guard's already-captured
            # output if this dispatcher accumulated instead of flushing.
            _rc, out, err = _invoke(getattr(mod, "main"), raw)
        except BaseException:
            skipped.append(guard.module_key)
            continue
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

    if skipped:
        sys.__stderr__.write(
            "[sessionstart-async-dispatch] guard(s) skipped (fail-open for those only): "
            + ", ".join(skipped) + "\n"
        )
        sys.__stderr__.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
