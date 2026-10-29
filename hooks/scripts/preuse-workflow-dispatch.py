"""PreToolUse(Workflow) fan-in dispatcher -- the engine submission stage, then seven
legs, behind one hooks.json Workflow-matcher registration, one interpreter.

ENGINE SUBMISSION STAGE (runs before REGISTRY, not a leg). A Workflow call naming the
plugin's `engine-ask` stub (`workflows/engine-ask.js`) or `bug-blitz` stub
(`workflows/bug-blitz.js`) is the EM's submission: it is handed to the engine op the
SUBMISSIONS table maps the stub to (`hooks.submit_engine_ask`, `hooks.submit_bug_blitz`)
through the settings-home `hook-run` door, which emits the warp run and answers allow + a
rewrite to the emitted script. Each stub's deny carries its own tail: retry once, then the
hand route (engine-ask: do the work by hand; bug-blitz: run the grind by hand), filing the failure to the engine owner. Its rewrite IS the payload every leg below judges, so the receipt legs verify the
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
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

#: A sibling module that fails to import is held, not raised: `main` turns it into a named deny
#: for a submission and re-raises it for any other call.
_IMPORT_FAILURE: Optional[BaseException] = None
try:
    from _stop_family_runner import _BufferedTextCapture  # noqa: E402
    from _win_portability import no_console_creationflags  # noqa: E402
except Exception as _exc:  # pragma: no cover - exercised by forcing the import to fail
    _IMPORT_FAILURE = _exc

try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    def _git_root_walk(start: Optional[str] = None) -> Optional[str]:  # type: ignore[no-redef]
        return None

try:
    from _protected_act import advise_and_record as _advise_and_record  # noqa: E402
    from _protected_act import protected_act_for as _protected_act_for  # noqa: E402
except Exception:
    def _protected_act_for(guard_id: str, roster_path: Any = None) -> Optional[str]:  # type: ignore[no-redef]
        return None

    def _advise_and_record(guard_id: str, deny_text: str, event: str, repo: Any = None) -> None:  # type: ignore[no-redef]
        return None


def _stands(env: Optional[dict], guard_id: str) -> bool:
    """True when `env` is a deny whose guard declares a protected act. Any other deny is
    recorded to the friction log and dropped, injecting nothing."""
    if _hso(env).get("permissionDecision") != "deny":
        return False
    if _protected_act_for(guard_id) is not None:
        return True
    _advise_and_record(guard_id, str(_hso(env).get("permissionDecisionReason") or ""), "PreToolUse")
    return False


#: Stub name -> the engine op that turns its submission into the fired run.
SUBMISSIONS: Mapping[str, str] = {
    "engine-ask": "hooks.submit_engine_ask",
    "bug-blitz": "hooks.submit_bug_blitz",
}
#: The hand route a denied submission names after one retry, per stub.
_DENY_TAILS: Mapping[str, str] = {
    "hooks.submit_engine_ask": (
        "do the work by hand (dispatch the agents yourself, scoped commits) "
        "and file this failure to claude-klabauter-em."
    ),
    "hooks.submit_bug_blitz": (
        "run the grind by hand (dispatch the agents yourself, scoped commits) "
        "and file this failure to claude-klabauter-em."
    ),
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
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            return None
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
            "skipped: no hook-run launcher; nothing was emitted"
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
        "). Check warm.request_status, retry once, then " + deny_tail
    )
    room = 280 - len(lead) - len(tail)
    if len(crumb) > room:
        crumb = crumb[: room - 3] + "..."
    return _deny(lead + crumb + tail)


_REFUSAL_LEAD = "The engine took this submission but emitted no run: "
#: The longest deny tail bounds the words room, so every stub's refusal fits the cap.
_REFUSAL_REMEDY = " Fix the args and retry once; if it still refuses, "
_REFUSAL_WORDS_CAP = 280 - len(_REFUSAL_LEAD) - len(_REFUSAL_REMEDY) - max(
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
    return _deny(_REFUSAL_LEAD + said + _REFUSAL_REMEDY + deny_tail)


#: What this call wrote to stdout, for the per-call log line.
_EMITTED: List[str] = []
_CALL_LOG_GUARD_ID = "preuse-workflow-dispatch.py:call"
_call_record = _advise_and_record


def _outcome() -> str:
    text = "".join(_EMITTED)
    if not text.strip():
        return "passed"
    if "The engine did not take this submission" in text:
        return "unreached"
    if '"permissionDecision": "deny"' in text:
        return "denied"
    return "allowed"


def _log_call(raw: str) -> None:
    """One line per call to the friction log: the call id and the outcome. Never raises."""
    try:
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        call_id = payload.get("tool_use_id") if isinstance(payload, dict) else None
        _call_record(
            _CALL_LOG_GUARD_ID,
            f"call_id={call_id or '-'} outcome={_outcome()}",
            "PreToolUse",
        )
    except Exception:
        return None


def _write_bytes(stream: Any, text: str) -> None:
    if stream is sys.stdout:
        _EMITTED.append(text)
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
        reason = hso.get("permissionDecisionReason")
        has_reason = isinstance(reason, str) and bool(reason.strip())
        # A bare allow carrying only advisory context is an advisory, not a grant.
        advisory_only = (
            not has_reason
            and not isinstance(hso.get("updatedInput"), dict)
            and isinstance(hso.get("additionalContext"), str)
            and bool(hso["additionalContext"].strip())
        )
        if hso.get("permissionDecision") == "allow" and not advisory_only:
            allowed = True
            if has_reason:
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


_SUBMISSION_NAME_RE = re.compile(r'(?<![A-Za-z_])name\\?"\s*:\s*\\?"(?:[^"\\]*:)?(engine-ask|bug-blitz)')
_WORKFLOW_TOOL_RE = re.compile(r'"tool_name"\s*:\s*"Workflow"')


def _submission_op(raw: str) -> Optional[str]:
    """The engine op when `raw` is submission-shaped, even if it does not parse as JSON.
    Never raises: the failure paths call it to decide between a named deny and a pass."""
    try:
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            return _is_submission(payload)
        if _WORKFLOW_TOOL_RE.search(raw):
            found = _SUBMISSION_NAME_RE.search(raw)
            if found:
                return SUBMISSIONS[found.group(1)]
    except Exception:
        return None
    return None


def main() -> int:
    """Run the dispatcher; any failure on a submission-shaped call is a named deny, never silence."""
    raw = sys.stdin.read()
    _EMITTED.clear()
    try:
        if _IMPORT_FAILURE is not None:
            raise _IMPORT_FAILURE
        rc = _dispatch(raw)
    except Exception as exc:
        op = _submission_op(raw)
        if op is None:
            _log_call(raw)
            raise
        _write_bytes(
            sys.stdout,
            json.dumps(_unreached(f"hook failed: {type(exc).__name__}: {exc}", _DENY_TAILS[op])) + "\n",
        )
        rc = 0
    _log_call(raw)
    return rc


def _dispatch(raw: str) -> int:
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
    op = _is_submission(payload) if isinstance(payload, dict) else _submission_op(raw)
    if op is not None and not isinstance(payload, dict):
        _write_bytes(
            sys.stdout,
            json.dumps(_unreached("the call payload was not a JSON object", _DENY_TAILS[op])) + "\n",
        )
        return 0
    if op is not None:
        deny_tail = _DENY_TAILS[op]
        submitted, crumb = _engine_submission(op, raw, payload)
        if submitted is None:
            submitted = _unreached(crumb, deny_tail)
        fired = _hso(submitted).get("updatedInput")
        # A submission refusal is a floor guard: it denies at every guard level, so no
        # protected-act roster gate applies to the engine's deny or this stage's own.
        if _hso(submitted).get("permissionDecision") == "deny":
            _write_bytes(sys.stdout, json.dumps(submitted) + "\n")
            return 0
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
            if _stands(env, guard.filename):
                _flush_stderr()
                _write_bytes(sys.stdout, out)
                return 0
            continue
        envs.append(env)

    _flush_stderr()
    composed = _compose(envs)
    if composed:
        _write_bytes(sys.stdout, json.dumps(composed) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
