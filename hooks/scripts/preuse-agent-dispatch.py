"""PreToolUse(Agent) fan-in dispatcher -- four hooks.json Agent-matcher
registrations, one interpreter.

Folds `block-dispatch-suite-invocation.py`, `block-unenumerated-agent-type.py`,
`guard-review-integrator-sidecar-intake.py`, and `enforce-agent-dispatch-mode.py`
into ONE `python3` process on the Agent-matcher leg of PreToolUse, following the
same registry + dynamic-import pattern `stop-dispatch.py` already ships for the
Stop event (docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md's own
fold, state/audits/2026-08-16-doe-hook-consolidation-feasibility.md).

THIS IS HOSTING ONLY, NEVER A POLICY CHANGE. Same four guards, same deny/allow
text, same override hatches, same ordering, same fail-open/fail-closed contracts
each guard's own module docstring already states. This file adds ZERO judgement
of its own.

AGGREGATION CONTRACT -- FIRST-DENY-WINS, NON-DENY OUTPUT COMPOSES. Guards 1-3
run in registration order (each guard's own `hooks/REGISTRATIONS.md` section
states why it sits where it does); the FIRST one that denies short-circuits the
rest, guard 4 included, and its deny is emitted verbatim.

A non-deny envelope from guards 1-3 is never dropped:
  - `updatedInput` REPLACES `tool_input` for every later guard. Guard 2's
    engine verdict emits one (the inherited-Opus -> sonnet model switch), so
    guard 4 builds its own `updatedInput` from the already-rewritten input and
    its rewrite lands on top of guard 2's by construction.
  - `additionalContext` and `systemMessage` strings accumulate in order.
Guard 4 (`enforce-agent-dispatch-mode.py`) then runs on the rewritten payload.
A guard-4 deny is emitted verbatim. Otherwise ONE envelope is emitted: guard
4's `updatedInput` if it built one, else the last upstream `updatedInput`;
every accumulated `additionalContext`/`systemMessage` joined with a blank
line; guard 4's `permissionDecision` when it gave one, none otherwise (an
upstream rewrite is orthogonal to the allow/deny question).

FAILURE ISOLATION. Guards 1-3 each run inside their own `try/except
BaseException` -- one guard crashing skips only that guard (with a stderr
skipped-list breadcrumb) and the dispatcher proceeds to the next, mirroring
`stop-dispatch.py`'s per-guard isolation. Guard 2
(block-unenumerated-agent-type.py) handles its own unreachable-engine legs
inside `main()` by passing loudly, so this wrapper only ever catches a genuine
crash in the invocation plumbing.

Guard 4 (`enforce-agent-dispatch-mode.py`) is NOT wrapped in the same
try/except -- its own `main()` already exits 0 unconditionally with
allow/nothing/deny conveyed via stdout only (its own docstring: "This hook exits 0 unconditionally"), so an
uncaught exception in it would be a genuine bug in that file, not a runtime
condition this dispatcher needs to paper over -- consistent with how it ran
standalone before this fold (a crash there previously took the whole
registration down too; this preserves that, rather than silently
downgrading a real bug to a skip).

LAZY IMPORT. Each guard module is imported via `importlib.util.spec_from_file_
location` only when reached (i.e. only after every earlier guard has declined
to deny) -- the all-miss path (the overwhelming majority of Agent dispatches:
no suite-shaped prompt, an enumerated subagent_type, not review-integrator,
nothing for guard 4 to elevate/provision/strip/reroute) still imports and
runs all four, because each guard's OWN internal logic is already the cheap
early-exit (a json.loads + a few field checks before any heavier work) --
there is no cheaper precondition to gate the import itself on without
duplicating each guard's own internal branching. See this dispatch's own
run-report for the measured all-miss-path cost this yields.

SHARED REPO ROOT. Two of the four guards define a module-level `_git_root`
name (`block-dispatch-suite-invocation.py`'s zero-arg `_git_root()`,
`guard-review-integrator-sidecar-intake.py`'s one-arg `_git_root(start)`) --
both are best-effort upward `.git` walks from the session cwd, computed
independently in the 4-process world. This dispatcher resolves the repo root
ONCE via `_git_root_walk.git_root_walk()` (stdlib-only, zero-spawn) and
replaces each guard's own `_git_root` name with a shim accepting either
call shape (`lambda *a, **kw: _root`) after import -- never before, so a
guard's own module-level code (there is none here that calls `_git_root` at
import time) is unaffected. Does NOT reintroduce a `git rev-parse` spawn
anywhere. Guards 2 and 4 resolve a DIFFERENT root (the sibling engine-plane
checkout, via `_engine_root`'s own resolver) -- untouched, out of
scope for this shared-root injection.

Negative spec: do not add a fifth guard here without updating this module's
docstring and the `hooks.json` comment naming the fold set; do not collapse
the first-deny-wins short-circuit into concatenate-all; do not drop a non-deny
upstream envelope -- a rewrite that never reaches the harness is a silent
policy bypass.

Spec: state/audits/2026-08-16-doe-hook-consolidation-feasibility.md
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
from typing import Any, Callable, List, Optional, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

try:
    from _git_root_walk import git_root_walk as _git_root_walk
except Exception:
    def _git_root_walk() -> Optional[str]:  # type: ignore[no-redef]
        return None


@dataclass(frozen=True)
class AgentGuard:
    module_key: str
    filename: str


# Registration order == prior hooks.json registration order == first-deny-wins
# precedence. See module docstring "AGGREGATION CONTRACT".
REGISTRY: Tuple[AgentGuard, ...] = (
    AgentGuard("block_dispatch_suite_invocation", "block-dispatch-suite-invocation.py"),
    AgentGuard("block_unenumerated_agent_type", "block-unenumerated-agent-type.py"),
    AgentGuard("guard_review_integrator_sidecar_intake", "guard-review-integrator-sidecar-intake.py"),
    AgentGuard("enforce_agent_dispatch_mode", "enforce-agent-dispatch-mode.py"),
)


class _ByteSink:
    """Binary-mode facade for `_BufferedTextCapture.buffer`: writes bytes straight
    through, UNMODIFIED, into the SAME ordered `io.BytesIO` the text channel's
    `write(str)` encodes into -- no decode, no round-trip at capture time. Byte-
    exactness matters because a guard reached via this matcher may write raw
    UTF-8 bytes via `sys.stderr.buffer.write()` specifically to bypass Python's
    Windows text-mode CRLF translation (see `_stop_family_runner.py`'s `_ByteSink`
    docstring for the full rationale and the `project-orientation.py`/`_w()`
    convention this protects). This dispatcher's own re-emission (below) writes
    `.encode("utf-8")` through `sys.stdout.buffer`/`sys.stderr.buffer`, never the
    text wrapper, so that guarantee survives the round trip to the real process
    stdout/stderr."""

    def __init__(self, sink: "io.BytesIO") -> None:
        self._sink = sink

    def write(self, data: bytes) -> int:
        return self._sink.write(data)

    def flush(self) -> None:
        pass


class _BufferedTextCapture(io.StringIO):
    """Same shim `stop-dispatch.py`/`_stop_family_runner` use: some guards on
    this matcher may reach code paths that write via `sys.stderr.buffer`. Both
    channels land in ONE ordered `io.BytesIO` -- `write(str)` encodes into it,
    `.buffer.write(bytes)` writes into it unmodified -- so `combined()`/
    `combined_bytes()` are order-preserving AND byte-exact, rather than
    concatenating two separately-accumulated buffers."""

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


def _import_guard(guard: AgentGuard) -> Any:
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
    if hasattr(mod, "_git_root"):
        _root = _git_root_walk()
        mod._git_root = lambda *_a, _r=_root, **_kw: _r
    return mod


def _write_bytes(stream: Any, text: str) -> None:
    """Re-emits captured guard text to the REAL process stream via its `.buffer`,
    never the text wrapper -- `sys.stdout.write(str)`/`sys.stderr.write(str)` run
    through Windows text-mode CRLF translation, which would corrupt a guard's raw
    `sys.stdout.buffer.write()`/`sys.stderr.buffer.write()` bytes one hop after
    `_BufferedTextCapture` captured them byte-exact. See `_ByteSink`'s own
    docstring above."""
    stream.buffer.write(text.encode("utf-8"))
    stream.buffer.flush()


def _invoke(main_fn: Callable[[], int], stdin_text: str) -> Tuple[int, str, str]:
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


def _envelope(stdout_text: str) -> Optional[dict]:
    text = stdout_text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _hso(env: Optional[dict]) -> dict:
    hso = env.get("hookSpecificOutput") if env else None
    return hso if isinstance(hso, dict) else {}


def _is_deny(env: Optional[dict]) -> bool:
    return _hso(env).get("permissionDecision") == "deny"


def _collect_notes(env: Optional[dict], contexts: List[str], system_messages: List[str]) -> None:
    ctx = _hso(env).get("additionalContext")
    if isinstance(ctx, str) and ctx.strip():
        contexts.append(ctx)
    msg = env.get("systemMessage") if env else None
    if isinstance(msg, str) and msg.strip():
        system_messages.append(msg)


def _skipped_line(skipped: List[str]) -> str:
    return (
        "[preuse-agent-dispatch] guard(s) skipped (fail-open for those only): "
        + ", ".join(skipped)
    )


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload: Any = json.loads(raw)
    except Exception:
        payload = None

    skipped: List[str] = []
    trailing_stderr: List[str] = []
    contexts: List[str] = []
    system_messages: List[str] = []
    upstream_input: Optional[dict] = None

    # Guards 1-3: first-deny-wins, isolated; non-deny output composes.
    for guard in REGISTRY[:-1]:
        try:
            mod = _import_guard(guard)
            rc, out, err = _invoke(getattr(mod, "main"), raw)
        except BaseException:
            skipped.append(guard.module_key)
            continue
        if err.strip():
            trailing_stderr.append(err.rstrip("\n"))
        env = _envelope(out)
        if _is_deny(env):
            if skipped:
                trailing_stderr.append(_skipped_line(skipped))
            if trailing_stderr:
                _write_bytes(sys.stderr, "\n".join(trailing_stderr) + "\n")
            _write_bytes(sys.stdout, out)
            return 0
        _collect_notes(env, contexts, system_messages)
        rewritten = _hso(env).get("updatedInput")
        if isinstance(rewritten, dict) and rewritten and isinstance(payload, dict):
            upstream_input = rewritten
            payload["tool_input"] = rewritten
            raw = json.dumps(payload)

    # Guard 4 runs on the (possibly rewritten) payload. NOT isolated -- see
    # module docstring.
    last = REGISTRY[-1]
    mod = _import_guard(last)
    rc, out, err = _invoke(getattr(mod, "main"), raw)
    if err.strip():
        trailing_stderr.append(err.rstrip("\n"))
    if skipped:
        trailing_stderr.append(_skipped_line(skipped))
    if trailing_stderr:
        _write_bytes(sys.stderr, "\n".join(trailing_stderr) + "\n")

    env = _envelope(out)
    if _is_deny(env) or (out.strip() and env is None):
        _write_bytes(sys.stdout, out)
        return 0
    _collect_notes(env, contexts, system_messages)

    hso = dict(_hso(env))
    if not isinstance(hso.get("updatedInput"), dict) and upstream_input is not None:
        hso["updatedInput"] = upstream_input
    if contexts:
        hso["additionalContext"] = "\n\n".join(contexts)
    if not hso:
        if system_messages:
            _write_bytes(sys.stdout, json.dumps(
                {"systemMessage": "\n\n".join(system_messages)}
            ) + "\n")
        return 0
    hso["hookEventName"] = "PreToolUse"
    merged = dict(env or {})
    merged["hookSpecificOutput"] = hso
    if system_messages:
        merged["systemMessage"] = "\n\n".join(system_messages)
    _write_bytes(sys.stdout, json.dumps(merged) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
