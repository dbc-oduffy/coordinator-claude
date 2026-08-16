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

AGGREGATION CONTRACT -- FIRST-DENY-WINS, NOT CONCATENATE-ALL. This is the one
place this dispatcher's shape differs from `stop-dispatch.py` (Stop's five
guards concatenate every firing advisory) and from `preuse-write-dispatch.py`
(the Write/Edit/MultiEdit guards may each independently advise). The four
Agent-matcher guards were ALREADY ordered in `hooks.json` on the documented
precedent of "first-deny-wins in registration order" (see each guard's own
`hooks.json` `_comment`: block-dispatch-suite-invocation.py "Registered first
in this matcher's hook list so its deny is not shadowed"; block-unenumerated-
agent-type.py "Registered at index 4 -- after the DR-088 suite guard ... and
ahead of every advisory Agent entry that follows, so this hard deny is never
shadowed"). `enforce-agent-dispatch-mode.py` is the ONLY guard on this matcher
that ever emits `permissionDecision: allow` + `updatedInput` (its own module
docstring: "the ONLY updatedInput emitter on the Agent matcher") -- every
other guard here only ever emits a deny or nothing. Preserving that single-
emitter invariant is therefore automatic in THIS shape: guards 1-3 run first,
in their prior registration order, and the FIRST one that denies short-
circuits the rest (enforce-agent-dispatch-mode.py included) -- exactly what
first-deny-wins already meant when these were four parallel registrations
racing the harness's own undefined same-event completion order. Only once
none of guards 1-3 deny does guard 4 run, and its own output (deny, allow, or
nothing) is emitted verbatim.

FAILURE ISOLATION. Guards 1-3 each run inside their own `try/except
BaseException` -- one guard crashing skips only that guard (with a stderr
skipped-list breadcrumb) and the dispatcher proceeds to the next, mirroring
`stop-dispatch.py`'s per-guard isolation. NAMED RESIDUAL, not a defect: guard 2
(block-unenumerated-agent-type.py) documents its own fail-CLOSED behaviour on
a *transport* failure (unresolvable engine root, unimportable engine module, a
raising `check()` call) -- but that behaviour is encoded INSIDE its own `main()`
via internal try/excepts that emit a deny JSON, so `main()` itself does not
raise on any of the failure modes its own docstring names; this dispatcher's
outer isolation wrapper is a defence-in-depth catch for a genuinely unexpected
crash in THIS file's own invocation plumbing (a bug in `_invoke`, a malformed
`sys.modules` entry, etc.), and on that narrow residual it fails OPEN for
guard 2 same as every other guard here, converting the guard's own fail-closed
contract to fail-open only in a case that contract's own docstring never
claimed to cover. This is named, not silently accepted: see the ANTI-DODGE
note in this dispatch's run-report.

Guard 4 (`enforce-agent-dispatch-mode.py`) is NOT wrapped in the same
try/except -- it is the sole `updatedInput` emitter and its own `main()`
already exits 0 unconditionally with allow/nothing/deny conveyed via stdout
only (its own docstring: "This hook exits 0 unconditionally"), so an
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
the first-deny-wins short-circuit into concatenate-all -- the two guards this
matcher used to race (worktree strip / named-dispatch strip / foreground
reroute) were ALREADY folded into `enforce-agent-dispatch-mode.py` itself as
single-emitter Concerns E/F/G before this dispatch (2026-07-31); this file
does not re-open that.

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


def _is_deny(stdout_text: str) -> bool:
    text = stdout_text.strip()
    if not text:
        return False
    try:
        obj = json.loads(text)
    except Exception:
        return False
    if not isinstance(obj, dict):
        return False
    hso = obj.get("hookSpecificOutput")
    return isinstance(hso, dict) and hso.get("permissionDecision") == "deny"


def main() -> int:
    raw = sys.stdin.read()

    skipped: List[str] = []
    trailing_stderr: List[str] = []

    # Guards 1-3: first-deny-wins, isolated.
    for guard in REGISTRY[:-1]:
        try:
            mod = _import_guard(guard)
            rc, out, err = _invoke(getattr(mod, "main"), raw)
        except BaseException:
            skipped.append(guard.module_key)
            continue
        if err.strip():
            trailing_stderr.append(err.rstrip("\n"))
        if _is_deny(out):
            if skipped:
                _write_bytes(sys.stderr, "\n".join(trailing_stderr + [
                    "[preuse-agent-dispatch] guard(s) skipped (fail-open for "
                    "those only): " + ", ".join(skipped)
                ]) + "\n")
            elif trailing_stderr:
                _write_bytes(sys.stderr, "\n".join(trailing_stderr) + "\n")
            _write_bytes(sys.stdout, out)
            return 0

    # Guard 4: the sole updatedInput emitter, only reached once none of
    # guards 1-3 denied. NOT isolated -- see module docstring.
    last = REGISTRY[-1]
    mod = _import_guard(last)
    rc, out, err = _invoke(getattr(mod, "main"), raw)
    if err.strip():
        trailing_stderr.append(err.rstrip("\n"))
    if skipped:
        trailing_stderr.append(
            "[preuse-agent-dispatch] guard(s) skipped (fail-open for those "
            "only): " + ", ".join(skipped)
        )
    if trailing_stderr:
        _write_bytes(sys.stderr, "\n".join(trailing_stderr) + "\n")
    if out.strip():
        _write_bytes(sys.stdout, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
