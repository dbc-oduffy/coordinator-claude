"""Stop-event fan-in dispatcher -- six hooks.json Stop registrations, one interpreter.

Folds `runtime-tripwire-em-check.py`, `nudge-harness-directive-dispatch.py`,
`nudge-unrouted-sizing.py`, `watchdog-undischarged-next-move.py`,
`guard-manufactured-blocker.py`, and `stop-em-report-altitude.py` into ONE
`python3` process on the Stop event, following the registry +
lazy-scope-descriptor pattern `preuse-write-dispatch.py` / `_guard_runner.py`
already ships (fan-in WITHIN one event, never pooling ACROSS events -- see
`test_bash_guard_hook_stays_per_event.py`, which this dispatcher does not
touch).

`stop-em-report-altitude.py` (the sixth entry, added after the MEASURED
figure below was taken) is the DoE-side wiring for the EM->PM comms-budget
advisory op `hooks.em_report_altitude` -- see that shim's own docstring for
its channel/no-op contract. Prior to this entry, that engine op had NO
DoE-side caller anywhere in this plugin and its advisory never fired; this
is NOT one of the five guards `runtime-tripwire-em-check.py` already
carries live, despite an earlier stale docstring clause here claiming
otherwise.

MEASURED (state/audits/2026-08-16-doe-hook-consolidation-feasibility.md):
5 processes/477.9ms -> 1 process/110.7ms on the all-miss path (4.3x), min-of-15
round-robin interleaved. Prototype verified guard-by-guard against a real Stop
payload and a real 674KB transcript before this file was authored -- this is a
hosting change, not a policy change: same advisories, same text, same emission
conditions, same ordering and dedup as the five standalone scripts.

Aggregation contract, copied from `_stop_family_runner.run_stop_family_guards`:
CONCATENATE-ALL, never first-fires-wins. Combined exit is 2 if ANY guard
returned 2; combined stderr is every firing guard's text joined by a blank
line; stdout (the posture-scaled advisory channel two of these guards use) is
concatenated separately and always emitted. Every guard runs inside its own
`try/except BaseException` -- one guard crashing removes only that guard
(fail-open for it alone, with a stderr skipped-list breadcrumb), exactly as
both shipped runners do (`_guard_runner.run_guards`,
`_stop_family_runner.run_stop_family_guards` clause 5,
`preuse-write-dispatch._compose_skipped_guard_breadcrumb`).

Lazy scope descriptors: each guard carries an import-free `precondition(ctx)`;
a guard whose precondition misses is never imported at all -- the all-miss
path is what nearly every turn end actually is, and is the dispatcher's whole
win over the eager "same work, one process" figure (236.3ms).

Shared repo root: resolved ONCE via `_git_root_walk.git_root_walk()` (stdlib-
only, zero-spawn in-process parent walk) and handed to any guard module that
exposes its own `_git_root` name, replacing that module's own (already-mostly-
zero-spawn) resolution with the value this dispatcher already computed --
avoids `runtime-tripwire-em-check.py` re-walking the tree a second time in the
same process. Does NOT reintroduce a `git rev-parse` spawn anywhere.

`watchdog-undischarged-next-move.py` is ALSO registered on
PostToolUse(Skill|Agent) -- untouched by this dispatcher, which only replaces
its Stop-event registration.

Negative spec: do not add a seventh guard here without updating this module's
docstring and the hooks.json comment naming the fold set; do not reintroduce a
`COORDINATOR_STOP_DISPATCH_LAZY`-style eager fallback path in production (the
lazy+shared-root config is the only shipped behaviour -- the eager mode lived
only in the feasibility prototype to produce an honest "same work" comparison
number and has no reason to exist here).

C2b restore procedure (asyncRewake stop-watcher, stood down 2026-07-31 per PM
ruling, script retained on disk untouched, not deleted): re-add a Stop
registration (matcher "", timeout 1800, async true, asyncRewake true, invoking
`runtime-tripwire-stop-watcher.py` via the standard runpy trampoline every
other hooks.json entry uses). There is no longer a constant to flip: the
`_SUBAGENT_OVERRUN_TRIPWIRE_ENABLED` gate and the ~530 lines it guarded were
excised from `runtime-tripwire-em-check.py` at `2b16d4db8`, so a restore means
reconstituting that code from git history -- recipe preserved verbatim in
`archive/debt-backlog/2026-08/2026-08-29-runtime-tripwire-em-check-py-four-overengin-a1f27c2e8c.yaml`
-- and it still waits on the engine-side durable subagent-arrival record that
was always its prerequisite. That script's remaining advisories (push-failure /
hooks.json-staleness / zero-tool-use / session-baton-mint) are unrelated and
stay live regardless.

Spec: state/audits/2026-08-16-doe-hook-consolidation-feasibility.md
Prototype this file productionises: (session scratchpad) stop-dispatch.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

try:
    from _git_root_walk import git_root_walk as _git_root_walk
except Exception:
    def _git_root_walk() -> Optional[str]:  # type: ignore[no-redef]
        return None

_TAIL_BYTES = 262144


# --------------------------------------------------------------------------
# Shared context: work every guard would otherwise redo in its own process.
# --------------------------------------------------------------------------
class Ctx:
    """Computed ONCE per Stop event and shared by all six preconditions.

    In the original 5-process world each of these was paid up to 5 times: the
    transcript tail was read by 3 of the 5 guards, and the repo root walked
    by 2. The sixth guard (`stop-em-report-altitude.py`) reuses this same
    shared `final_assistant_text()` memoisation.
    """

    def __init__(self, raw: str) -> None:
        self.raw = raw
        try:
            p = json.loads(raw) if raw else {}
            self.payload = p if isinstance(p, dict) else {}
        except Exception:
            self.payload = {}
        self.session_id = self.payload.get("session_id") or ""
        self.agent_id = self.payload.get("agent_id") or ""
        self.stop_hook_active = bool(self.payload.get("stop_hook_active"))
        self.transcript_path = self.payload.get("transcript_path") or ""
        self._tail: Optional[str] = None
        self._repo_root: Optional[str] = None

    # -- lazy, memoised: only paid if some precondition actually asks
    def tail(self) -> str:
        if self._tail is None:
            self._tail = ""
            try:
                if self.transcript_path and os.path.isfile(self.transcript_path):
                    size = os.path.getsize(self.transcript_path)
                    with open(self.transcript_path, "rb") as fh:
                        if size > _TAIL_BYTES:
                            fh.seek(size - _TAIL_BYTES)
                        self._tail = fh.read().decode("utf-8", "replace")
            except Exception:
                self._tail = ""
        return self._tail

    def final_assistant_text(self) -> str:
        last = ""
        for line in self.tail().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "assistant":
                continue
            msg = entry.get("message")
            content = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(content, list):
                continue
            parts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            last = "\n".join(parts) if parts else ""
        return last

    def repo_root(self) -> str:
        if self._repo_root is None:
            self._repo_root = _git_root_walk() or ""
        return self._repo_root


# --------------------------------------------------------------------------
# Preconditions -- import-free, cheapest-first. Each returns True only if the
# guard's expensive module import can possibly matter.
# --------------------------------------------------------------------------
def _pre_em_check(ctx: Ctx) -> bool:
    # em-check exits 0 immediately without a session_id or a git root; both
    # are payload/one-stat cheap, and the git walk is shared.
    return bool(ctx.session_id) and bool(ctx.repo_root())


def _pre_next_move(ctx: Ctx) -> bool:
    # The watchdog reads the per-session next-move ledger AND NOTHING ELSE.
    # No ledger file for this session -> the guard is provably a no-op.
    #
    # The path and extension MUST track `_next_move_ledger.py`'s own
    # `_LEDGER_FILENAME` and storage root, which are its docstring's contract:
    # `state/subagent-share/<session-id>/next-move-ledger.jsonl`. This
    # precondition previously named `.git/coordinator-sessions/<sid>/
    # next-move-ledger.json` -- the pre-2026-08-15 location, and a `.json`
    # extension the writer has never used. Wrong on both axes, it returned
    # False for every session, and the Stop leg it gates never ran once
    # between the C2 anchoring (471e8eba8) and this fix. A precondition that
    # is always False is indistinguishable on disk from a predicate that
    # never has anything to say; the tell was 123 ledgers at the real path
    # and 0 at this one.
    #
    # The two literals below are duplicated rather than imported ON PURPOSE:
    # this precondition runs before any guard module is imported, and pulling
    # in `_next_move_ledger` (and transitively `_engine_root`) here would pay
    # that import on every Stop in the fleet to answer a one-`stat` question.
    # The duplication is pinned instead --
    # `test_stop_precondition_tracks_the_ledgers_real_path` asserts both
    # against the writer's own constants, so the drift that killed this leg
    # cannot reland silently.
    root = ctx.repo_root()
    if not root or not ctx.session_id:
        return False
    return os.path.isfile(
        os.path.join(root, "state", "subagent-share", ctx.session_id,
                     "next-move-ledger.jsonl")
    )


def _pre_manufactured_blocker(ctx: Ctx) -> bool:
    if ctx.agent_id or ctx.stop_hook_active:
        return False
    return bool(ctx.final_assistant_text())


def _pre_transcript_present(ctx: Ctx) -> bool:
    # The two engine-backed pointer shims both work off the final assistant
    # message; no transcript, no possible fire.
    return bool(ctx.final_assistant_text())


def _pre_em_report_altitude(ctx: Ctx) -> bool:
    # em_report_altitude measures the final assistant message; a subagent's
    # own Stop (agent_id present) is never an EM->PM message, and no final
    # assistant text means nothing to measure either way.
    if ctx.agent_id:
        return False
    return bool(ctx.final_assistant_text())


def _pre_receiver_state(ctx: Ctx) -> bool:
    # The producer shim needs a session_id and this session's own transcript;
    # without either the op is a silent no-op engine-side, so skip the import
    # entirely. Deliberately does NOT read the transcript -- `os.path.isfile`
    # only, never `ctx.tail()`: the ladder is the engine's, and paying a tail
    # read here to decide whether to let the engine do its own tail read would
    # double the cost to answer nothing.
    if not ctx.session_id:
        return False
    return bool(ctx.transcript_path) and os.path.isfile(ctx.transcript_path)


@dataclass(frozen=True)
class StopGuard:
    module_key: str
    filename: str
    precondition: Callable[[Ctx], bool]


REGISTRY: Tuple[StopGuard, ...] = (
    StopGuard("runtime_tripwire_em_check", "runtime-tripwire-em-check.py", _pre_em_check),
    StopGuard("nudge_harness_directive_dispatch",
              "nudge-harness-directive-dispatch.py", _pre_transcript_present),
    StopGuard("nudge_unrouted_sizing", "nudge-unrouted-sizing.py", _pre_transcript_present),
    StopGuard("watchdog_undischarged_next_move",
              "watchdog-undischarged-next-move.py", _pre_next_move),
    StopGuard("guard_manufactured_blocker",
              "guard-manufactured-blocker.py", _pre_manufactured_blocker),
    StopGuard("stop_em_report_altitude",
              "stop-em-report-altitude.py", _pre_em_report_altitude),
    # A PRODUCER, not a guard -- it always exits 0 with empty stdout, so it
    # contributes nothing to this dispatcher's CONCATENATE-ALL aggregation and
    # cannot change any verdict. It rides the fan-in rather than taking a
    # second `Stop` entry in hooks.json purely for the process cost: a second
    # entry buys a permanent extra interpreter cold start on every Stop
    # fleet-wide, where folding it here adds no process at all.
    StopGuard("receiver_state_sensor",
              "receiver-state-sensor.py", _pre_receiver_state),
)


class _ByteSink:
    """Binary-mode facade for `_BufferedTextCapture.buffer`: writes bytes straight
    through, UNMODIFIED, into the SAME ordered `io.BytesIO` the text channel's
    `write(str)` encodes into -- no decode, no round-trip at capture time. The
    nudge shims folded here emit through `sys.stderr.buffer.write()` specifically
    to bypass Windows text-mode CRLF translation (see `_stop_family_runner.py`'s
    `_ByteSink` docstring for the full rationale). This dispatcher's own
    re-emission (below) writes `.encode("utf-8")` through `sys.stdout.buffer`/
    `sys.stderr.buffer`, never the text wrapper, so that guarantee survives the
    round trip to the real process stdout/stderr."""

    def __init__(self, sink: "io.BytesIO") -> None:
        self._sink = sink

    def write(self, data: bytes) -> int:
        return self._sink.write(data)

    def flush(self) -> None:
        pass


class _BufferedTextCapture(io.StringIO):
    """Same shim `_stop_family_runner` uses: the nudge shims emit through
    `sys.stderr.buffer.write()`, which a plain StringIO has no attribute for.
    Both channels land in ONE ordered `io.BytesIO` -- `write(str)` encodes
    into it, `.buffer.write(bytes)` writes into it unmodified -- so
    `combined()`/`combined_bytes()` are order-preserving AND byte-exact,
    rather than concatenating two separately-accumulated buffers."""

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


def _import_guard(guard: StopGuard) -> Any:
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


def _invoke(main_fn: Callable[[], int], stdin_text: str) -> Tuple[int, str, str]:
    """Run one guard's main() with stdin swapped and BOTH channels captured.

    Stop guards use stderr+exit 2 to speak to Claude and stdout+exit 0 for the
    posture-scaled advisory channel, so unlike `_stop_family_runner` (stderr
    only) this dispatcher must capture and merge both.
    """
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
    return (rc or 0), out_buf.combined(), err_buf.combined()


def main() -> int:
    raw = sys.stdin.read()
    ctx = Ctx(raw)

    fired_err: List[str] = []
    advisory_out: List[str] = []
    skipped: List[str] = []
    any_fired = False

    trace = os.environ.get("COORDINATOR_STOP_DISPATCH_TRACE") == "1"
    if trace:
        import time as _t

    for guard in REGISTRY:
        if trace:
            _t0 = _t.perf_counter()
        try:
            if not guard.precondition(ctx):
                if trace:
                    sys.stderr.write(
                        f"[trace] {guard.module_key}: PRE-MISS "
                        f"{(_t.perf_counter() - _t0) * 1000:.1f}ms\n")
                continue
        except BaseException:
            skipped.append(guard.module_key + " (precondition)")
            continue
        try:
            mod = _import_guard(guard)
            # SHARED-CONTEXT INJECTION -- the half of the win that is "better
            # code", not merely "fewer processes". Hands the module a repo
            # root already resolved by this dispatcher's own zero-spawn walk
            # rather than letting it re-derive its own (only possible once
            # the guards share an interpreter).
            if hasattr(mod, "_git_root"):
                _root = ctx.repo_root()
                mod._git_root = lambda _r=_root: _r
            if trace:
                _t1 = _t.perf_counter()
            rc, out, err = _invoke(getattr(mod, "main"), raw)
            if trace:
                sys.stderr.write(
                    f"[trace] {guard.module_key}: rc={rc} "
                    f"import={(_t1 - _t0) * 1000:.1f}ms "
                    f"run={(_t.perf_counter() - _t1) * 1000:.1f}ms\n")
        except BaseException as exc:
            # Exception isolation: this guard alone fails open; the other
            # four still run.
            skipped.append(guard.module_key)
            if trace:
                sys.stderr.write(f"[trace] {guard.module_key}: RAISED {exc!r}\n")
            continue
        if out.strip():
            advisory_out.append(out.rstrip("\n"))
        if rc == 2:
            any_fired = True
            if err.strip():
                fired_err.append(err.rstrip("\n"))

    if advisory_out:
        # Re-emit through .buffer, never the text wrapper -- advisory_out/
        # fired_err are built from _BufferedTextCapture.combined(), which may
        # carry a folded guard's raw sys.stdout.buffer.write()/sys.stderr.
        # buffer.write() bytes (Windows CRLF-translation fix); a text-mode
        # write here would reintroduce exactly the translation that
        # convention exists to avoid. See _ByteSink's own docstring above.
        _out_text = "\n\n".join(advisory_out) + "\n"
        sys.stdout.buffer.write(_out_text.encode("utf-8"))
        sys.stdout.buffer.flush()
    if fired_err:
        _err_text = "\n\n".join(fired_err) + "\n"
        sys.stderr.buffer.write(_err_text.encode("utf-8"))
        sys.stderr.buffer.flush()
    if skipped:
        sys.stderr.write(
            "[stop-dispatch] guard(s) skipped (fail-open for those only): "
            + ", ".join(skipped) + "\n"
        )
    return 2 if any_fired else 0


if __name__ == "__main__":
    sys.exit(main())
