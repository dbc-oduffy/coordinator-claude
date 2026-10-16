"""PreToolUse(Workflow) fan-in dispatcher -- the engine submission stage, then seven
legs, behind one hooks.json Workflow-matcher registration, one interpreter.

ENGINE SUBMISSION STAGE (runs before REGISTRY, not a leg). A Workflow call naming the
plugin's `engine-ask` stub (`workflows/engine-ask.js`) or `bug-blitz` stub
(`workflows/bug-blitz.js`) is the EM's submission: it is handed to the engine op the
SUBMISSIONS table maps the stub to (`hooks.submit_engine_ask`, `hooks.submit_bug_blitz`)
through the settings-home `hook-run` door, which emits the warp run and answers allow + a
rewrite to the emitted script. Each stub's deny carries its own tail (engine-ask: do not
size or dispatch by hand; bug-blitz: do not emit the grind by hand). Its rewrite IS the payload every leg below judges, so the receipt legs verify the
script the call will actually fire; its envelope composes first. Any other call skips the
stage without a spawn. Denied, final: an engine deny; a submission the engine does not answer
(no launcher, spawn failure, timeout, no envelope); and any answer, allow or empty, that
carries no `updatedInput.scriptPath`. The last carries the engine's own
`additionalContext`/`systemMessage` words, so a refusal reads as the engine's. The stub never
runs as if it were the run; its own halt covers the hook not firing.

Folds, in this order: `block-workflow-foreign-emission.py`,
`block-dispatch-suite-invocation.py`, `block-workflow-unmodeled-agent.py`,
`block-unharvested-canvas-dispatch.py`, `strip-worktree-isolation.py`, `nudge-workflow-authoring-trampoline.py`,
`allow-emitted-workflow-fire.py`. REGISTRY order is the prior hooks.json order.

HOSTING ONLY, NEVER A POLICY CHANGE: each guard keeps its own deny text,
override hatches, sentinels and fail-open contract.

WORKFLOW-FAN-IN-PRECEDENCE (the aggregation contract):
  - Every leg sees the same payload: the stdin payload, or the submission
    stage's rewrite of it. No rewrite threading between legs;
    `strip-worktree-isolation.py` is the sole `updatedInput` emitter among them.
  - Deny: the FIRST deny in REGISTRY order wins, is emitted verbatim, and later
    legs are neither imported nor run. Context from earlier non-deny legs is
    dropped. Intended delta from separate registrations: a later leg's side
    effects (e.g. the trampoline's once-per-session sentinel) do not happen on a
    denied call.
  - No deny: ONE envelope. `permissionDecision` is `allow` when any leg that ran
    allowed, else absent; `permissionDecisionReason` joins the allow-giving legs'
    reasons in REGISTRY order; `updatedInput` is the sole rewriter's; every
    `additionalContext` and `systemMessage` joins in REGISTRY order with a blank
    line. Nothing to say means no stdout.
  - `SystemExit` from a leg is a return, not a crash: its captured stdout is
    processed normally (foreign-emission denies via print then `sys.exit(0)`).

FAILURE ISOLATION: each leg runs in `try/except BaseException` (after the
SystemExit arm). A crashing leg is skipped with a stderr breadcrumb and the rest
still run. A leg whose non-empty stdout is not a JSON object is never a deny: it
gets a breadcrumb and is ignored. Exit 0 always. Leg stderr is re-emitted in
REGISTRY order for the legs that ran.

TRAP: this file must never contain a quoted `updatedInput` dict-key literal;
the envelope is built by subscript, else
`test_at_most_one_updated_input_emitter_per_matcher` counts it as a second
Workflow emitter.

Negative spec: do not reorder REGISTRY; do not thread rewrites between legs; do
not collapse first-deny-wins into concatenate-all; do not widen
`preuse-agent-dispatch.py` to this matcher; do not move the submission stage into
REGISTRY (a leg sees the original payload, and the receipt legs must see the fired one).
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _stop_family_runner import _BufferedTextCapture  # noqa: E402
from _win_portability import no_console_creationflags  # noqa: E402

try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    def _git_root_walk(start: Optional[str] = None) -> Optional[str]:  # type: ignore[no-redef]
        return None


#: Stub name -> the engine op that turns its submission into the fired run.
SUBMISSIONS: Mapping[str, str] = {
    "engine-ask": "hooks.submit_engine_ask",
    "bug-blitz": "hooks.submit_bug_blitz",
}
#: What a denied submission tells the EM not to do by hand, per stub.
_DENY_TAILS: Mapping[str, str] = {
    "hooks.submit_engine_ask": "do not size or dispatch by hand.",
    "hooks.submit_bug_blitz": "do not emit the grind by hand.",
}
#: Under the registration's own 15s: a warm emit measures ~0.4s.
_SUBMIT_TIMEOUT_S = 12


@dataclass(frozen=True)
class WorkflowGuard:
    module_key: str
    filename: str


REGISTRY: Tuple[WorkflowGuard, ...] = (
    WorkflowGuard("block_workflow_foreign_emission", "block-workflow-foreign-emission.py"),
    WorkflowGuard("block_dispatch_suite_invocation", "block-dispatch-suite-invocation.py"),
    WorkflowGuard("block_workflow_unmodeled_agent", "block-workflow-unmodeled-agent.py"),
    WorkflowGuard("block_unharvested_canvas_dispatch", "block-unharvested-canvas-dispatch.py"),
    WorkflowGuard("strip_worktree_isolation", "strip-worktree-isolation.py"),
    WorkflowGuard("nudge_workflow_authoring_trampoline", "nudge-workflow-authoring-trampoline.py"),
    WorkflowGuard("allow_emitted_workflow_fire", "allow-emitted-workflow-fire.py"),
)


def _import_leg(guard: WorkflowGuard) -> Any:
    """Load a leg's module the first time it is reached, with the shared `_git_root` shim."""
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


def _invoke(main_fn: Callable[[], int], stdin_text: str) -> Tuple[str, str]:
    """Run a leg's main on `stdin_text`; return its captured (stdout, stderr)."""
    old_stdin = sys.stdin
    out_buf = _BufferedTextCapture()
    err_buf = _BufferedTextCapture()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        sys.stdin = io.StringIO(stdin_text)
        try:
            main_fn()
        except SystemExit:
            pass
        finally:
            sys.stdin = old_stdin
    return out_buf.combined(), err_buf.combined()


def _is_submission(payload: dict) -> Optional[str]:
    """The engine op for a submission stub named by the call, else None."""
    tool_input = payload.get("tool_input")
    if payload.get("tool_name") != "Workflow" or not isinstance(tool_input, dict):
        return None
    name = tool_input.get("name")
    if not isinstance(name, str):
        return None
    for stub, op in SUBMISSIONS.items():
        if name == stub or name.endswith(":" + stub):
            return op
    return None


def _hook_run() -> Optional[Path]:
    """The settings-home door launcher; imported lazily so a non-submission call pays nothing."""
    try:
        from _engine_root import _settings_home
        home = _settings_home()
    except Exception:
        return None
    for name in ("hook-run", "hook-run.exe"):
        candidate = Path(home) / "bin" / name
        if candidate.is_file():
            return candidate
    return None


def _engine_submission(op: str, raw: str, payload: dict) -> Tuple[Optional[dict], str]:
    """The engine's envelope for a submission, and a stderr breadcrumb when it has none."""
    launcher = _hook_run()
    if launcher is None:
        return None, (
            "engine submission skipped: no hook-run launcher under the settings home; "
            "nothing was emitted"
        )
    cwd = payload.get("cwd")
    try:
        proc = subprocess.run(
            [str(launcher), op],
            input=raw.encode("utf-8"),
            capture_output=True,
            timeout=_SUBMIT_TIMEOUT_S,
            env={**os.environ, "COORDINATOR_DOOR_STDIN_MODE": "hook"},
            cwd=cwd if isinstance(cwd, str) and os.path.isdir(cwd) else None,
            **no_console_creationflags(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, (
            f"engine submission failed: {type(exc).__name__}; a run may have been emitted"
        )
    try:
        env = json.loads(proc.stdout.decode("utf-8", errors="replace") or "null")
    except ValueError:
        env = None
    if not isinstance(env, dict):
        return None, "engine submission answered no envelope; a run may have been emitted"
    return env, ""


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _unreached(crumb: str, deny_tail: str) -> dict:
    """The fail-closed deny for a submission the engine did not answer."""
    lead, tail = "The engine did not take this submission (", (
        "). Tell the PM the engine submit door is down; " + deny_tail
    )
    room = 280 - len(lead) - len(tail)
    if len(crumb) > room:
        crumb = crumb[: room - 3] + "..."
    return _deny(lead + crumb + tail)


_REFUSAL_LEAD = "The engine took this submission but emitted no run: "
#: The longest deny tail bounds the words room, so every stub's refusal fits the cap.
_REFUSAL_WORDS_CAP = 280 - len(_REFUSAL_LEAD) - len(" Tell the PM; ") - max(
    len(t) for t in _DENY_TAILS.values()
)


def _refused(env: dict, deny_tail: str) -> dict:
    """The deny for an answer with no rewrite, carrying the engine's own words."""
    hso = _hso(env)
    # The engine's own deny reason leads: advisories in the other fields can fill the
    # whole cap, and truncating from the end must cut them, never the refusal.
    words = [
        w.strip()
        for w in (
            hso.get("permissionDecisionReason"),
            hso.get("additionalContext"),
            env.get("systemMessage"),
        )
        if isinstance(w, str) and w.strip()
    ]
    said = " ".join(" ".join(words).split()) or "it said nothing."
    if len(said) > _REFUSAL_WORDS_CAP:
        said = said[: _REFUSAL_WORDS_CAP - 3] + "..."
    return _deny(_REFUSAL_LEAD + said + " Tell the PM; " + deny_tail)


def _write_bytes(stream: Any, text: str) -> None:
    stream.buffer.write(text.encode("utf-8"))
    stream.buffer.flush()


def _hso(env: dict) -> dict:
    hso = env.get("hookSpecificOutput")
    return hso if isinstance(hso, dict) else {}


def _compose(envs: List[dict]) -> Optional[dict]:
    """The single envelope the harness would have produced from the non-deny legs, or None."""
    reasons: List[str] = []
    contexts: List[str] = []
    messages: List[str] = []
    allowed = False
    rewrite: Optional[dict] = None
    for env in envs:
        hso = _hso(env)
        if hso.get("permissionDecision") == "allow":
            allowed = True
            reason = hso.get("permissionDecisionReason")
            if isinstance(reason, str) and reason.strip():
                reasons.append(reason)
        new_input = hso.get("updatedInput")
        if isinstance(new_input, dict):
            rewrite = new_input
        ctx = hso.get("additionalContext")
        if isinstance(ctx, str) and ctx.strip():
            contexts.append(ctx)
        msg = env.get("systemMessage")
        if isinstance(msg, str) and msg.strip():
            messages.append(msg)

    out_hso: Dict[str, Any] = {}
    if allowed:
        out_hso["permissionDecision"] = "allow"
        if reasons:
            out_hso["permissionDecisionReason"] = "\n\n".join(reasons)
    if rewrite is not None:
        out_hso["updatedInput"] = rewrite
    if contexts:
        out_hso["additionalContext"] = "\n\n".join(contexts)
    merged: Dict[str, Any] = {}
    if out_hso:
        out_hso["hookEventName"] = "PreToolUse"
        merged["hookSpecificOutput"] = out_hso
    if messages:
        merged["systemMessage"] = "\n\n".join(messages)
    return merged or None


def main() -> int:
    raw = sys.stdin.read()
    skipped: List[str] = []
    stderr_parts: List[str] = []
    envs: List[dict] = []

    def _flush_stderr() -> None:
        if skipped:
            stderr_parts.append(
                "[preuse-workflow-dispatch] guard(s) skipped (fail-open for those only): "
                + ", ".join(skipped)
            )
        if stderr_parts:
            _write_bytes(sys.stderr, "\n".join(stderr_parts) + "\n")

    payload: Any = None
    try:
        payload = json.loads(raw)
    except ValueError:
        pass
    op = _is_submission(payload) if isinstance(payload, dict) else None
    if op is not None:
        deny_tail = _DENY_TAILS[op]
        submitted, crumb = _engine_submission(op, raw, payload)
        if submitted is None:
            submitted = _unreached(crumb, deny_tail)
        if _hso(submitted).get("permissionDecision") == "deny":
            _write_bytes(sys.stdout, json.dumps(submitted) + "\n")
            return 0
        fired = _hso(submitted).get("updatedInput")
        if not (isinstance(fired, dict) and fired.get("scriptPath")):
            _write_bytes(sys.stdout, json.dumps(_refused(submitted, deny_tail)) + "\n")
            return 0
        payload["tool_input"] = fired
        raw = json.dumps(payload)
        envs.append(submitted)

    for guard in REGISTRY:
        try:
            mod = _import_leg(guard)
            out, err = _invoke(getattr(mod, "main"), raw)
        except BaseException:
            skipped.append(guard.module_key)
            continue
        if err.strip():
            stderr_parts.append(err.rstrip("\n"))
        if not out.strip():
            continue
        try:
            env = json.loads(out)
        except Exception:
            env = None
        if not isinstance(env, dict):
            skipped.append(f"{guard.module_key} (non-JSON stdout ignored)")
            continue
        if _hso(env).get("permissionDecision") == "deny":
            _flush_stderr()
            _write_bytes(sys.stdout, out)
            return 0
        envs.append(env)

    _flush_stderr()
    composed = _compose(envs)
    if composed:
        _write_bytes(sys.stdout, json.dumps(composed) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
