"""PreToolUse(Agent) fan-in dispatcher -- four guards behind one hooks.json
Agent-matcher registration, one interpreter (the fourth,
`guard-agent-model-pin.py`, has no hooks.json entry of its own).

Folds `block-dispatch-suite-invocation.py`, `block-unenumerated-agent-type.py`,
and `enforce-agent-dispatch-mode.py` into ONE `python3` process on the
Agent-matcher leg of PreToolUse, following the same registry + dynamic-import
pattern `stop-dispatch.py` already ships for the Stop event
(docs/plans/2026-08-06-hook-spawn-fan-in-finish-and-extend.md's own fold,
state/audits/2026-08-16-doe-hook-consolidation-feasibility.md).

THIS IS HOSTING ONLY, NEVER A POLICY CHANGE to the four guards: same deny/allow
text, override hatches, ordering, and fail-open/fail-closed contracts each
guard's own module docstring states. This file owns two judgements of its own.
The REPO-LESS CWD REFUSAL runs before guard 1: a sidecar-eligible dispatch
(policy `report_sidecar:`) whose payload `cwd` sits in no git repo -- a
multi-repo parent directory -- is denied, naming the repos the brief's absolute
paths point at. SubagentStart provisioning anchors on that cwd and cannot refuse,
so the child would start and then block. Fail-open on every unknowable input.
The other is the one advisory under SKILL-STAGE BRIEF ADVISORY below.

AGGREGATION CONTRACT -- FIRST-DENY-WINS, NON-DENY OUTPUT COMPOSES. Guards 1-3
run in registration order (each guard's own `hooks/REGISTRATIONS.md` section
states why it sits where it does); the FIRST one that denies short-circuits the
rest, guard 4 (the last) included, and its deny is emitted verbatim.

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
no suite-shaped prompt, an enumerated subagent_type, nothing for guard 4 to
elevate/provision/strip/reroute) still imports and runs all four, because
each guard's OWN internal logic is already the cheap early-exit (a json.loads
+ a few field checks before any heavier work) -- there is no cheaper
precondition to gate the import itself on without duplicating each guard's
own internal branching. See this dispatch's own run-report for the measured
all-miss-path cost this yields.

SHARED REPO ROOT. One of the four guards defines a module-level `_git_root`
name (`block-dispatch-suite-invocation.py`'s zero-arg `_git_root()`) -- a
best-effort upward `.git` walk from the session cwd. This dispatcher resolves
the repo root ONCE via `_git_root_walk.git_root_walk()` (stdlib-only,
zero-spawn) and replaces that guard's own `_git_root` name with a shim
accepting either call shape (`lambda *a, **kw: _root`) after import -- never
before, so a guard's own module-level code (there is none here that calls
`_git_root` at import time) is unaffected. Does NOT reintroduce a
`git rev-parse` spawn anywhere. Guards 2 and 4 resolve a DIFFERENT root (the
sibling engine-plane checkout, via `_engine_root`'s own resolver) --
untouched, out of scope for this shared-root injection.

SKILL-STAGE BRIEF ADVISORY (SKILL-STAGE-BRIEF-ADVISORY). The one check this
file owns rather than hosts: a non-coordinator Agent prompt naming two or more
of the skill stages in `_SKILL_STAGES` gets an `additionalContext` advisory
pointing at `Skill(coordinator:<stage>)`. Advisory only, never a deny; it runs
after the guards, so a deny suppresses it. One regex over the prompt, no import
or spawn -- it sits on the Agent hot path.

Negative spec: do not add a fourth guard here without updating this module's
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
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

try:
    from _git_root_walk import git_root_walk as _git_root_walk
    from _git_root_walk import git_roots_named_in_text as _git_roots_named_in_text
except Exception:
    def _git_root_walk(start: Optional[str] = None) -> Optional[str]:  # type: ignore[no-redef]
        return None

    def _git_roots_named_in_text(text: str, limit: int = 3) -> List[str]:  # type: ignore[no-redef]
        return []

try:
    import yaml as _yaml
except Exception:
    _yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class AgentGuard:
    module_key: str
    filename: str


# Registration order == prior hooks.json registration order == first-deny-wins
# precedence. See module docstring "AGGREGATION CONTRACT".
REGISTRY: Tuple[AgentGuard, ...] = (
    AgentGuard("block_dispatch_suite_invocation", "block-dispatch-suite-invocation.py"),
    AgentGuard("block_unenumerated_agent_type", "block-unenumerated-agent-type.py"),
    AgentGuard("guard_agent_model_pin", "guard-agent-model-pin.py"),
    AgentGuard("enforce_agent_dispatch_mode", "enforce-agent-dispatch-mode.py"),
)


_SKILL_STAGES = ("sizing", "plan-blitz", "mise-prep", "mise-en-place")
_SKILL_STAGE_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(s) for s in _SKILL_STAGES) + r")(?![\w-])",
    re.IGNORECASE,
)


def _skill_stage_advisory(payload: Any) -> Optional[str]:
    """Advisory text when a non-coordinator Agent prompt names >= 2 distinct
    skill stages; None otherwise."""
    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    agent_type = tool_input.get("subagent_type")
    if isinstance(agent_type, str) and agent_type.startswith("coordinator:"):
        return None
    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str):
        return None
    named = {m.lower() for m in _SKILL_STAGE_RE.findall(prompt)}
    if len(named) < 2:
        return None
    stages = [s for s in _SKILL_STAGES if s in named]
    return (
        "SKILL-STAGE-BRIEF-ADVISORY: this Agent prompt briefs a worker to run "
        + ", ".join(stages)
        + ". These are skills, not a worker's checklist: invoke "
        + ", ".join(f"Skill(coordinator:{s})" for s in stages)
        + " instead."
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


def _sidecar_eligible(subagent_type: str) -> bool:
    """True when the policy's `report_sidecar:` list names this type. Fail-open: an
    unreadable policy or absent `yaml` module answers False, so nothing is refused."""
    policy_file = _HOOKS_DIR.parents[1] / "subagent-sandbox-policy.yaml"
    if _yaml is None or not policy_file.is_file():
        return False
    try:
        policy = _yaml.safe_load(policy_file.read_text(encoding="utf-8"))
        eligible = policy.get("report_sidecar") if isinstance(policy, dict) else None
        return isinstance(eligible, list) and subagent_type in eligible
    except Exception:
        return False


def _repo_less_cwd_refusal(payload: Any) -> Optional[str]:
    """Deny text for a sidecar-eligible dispatch whose payload `cwd` sits in no git repo.

    The SubagentStart sidecar provisioner anchors on that cwd; with no repo above it the child
    starts, then blocks with no scaffold. Refusing here names the fix while the EM can still act
    on it. Only a payload-carried cwd is judged -- an absent one is unknowable, never refused.
    """
    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return None
    cwd = payload.get("cwd")
    tool_input = payload.get("tool_input")
    if not isinstance(cwd, str) or not cwd or not isinstance(tool_input, dict):
        return None
    subagent_type = tool_input.get("subagent_type")
    if not isinstance(subagent_type, str) or _git_root_walk(cwd) is not None:
        return None
    if not _sidecar_eligible(subagent_type.strip()):
        return None
    prompt = tool_input.get("prompt")
    roots = _git_roots_named_in_text(prompt if isinstance(prompt, str) else "")
    if roots:
        fix = "cd into the repo this brief names (" + ", ".join(roots) + ") and redispatch."
    else:
        fix = "cd into the target repo and redispatch."
    return (
        f"[preuse-agent-dispatch] DISPATCH REFUSED: cwd `{cwd}` is not inside a git repo, so "
        f"`{subagent_type}` could not be given its run-report sidecar -- the subagent would "
        f"start, then block. Fix: {fix}"
    )


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload: Any = json.loads(raw)
    except Exception:
        payload = None

    refusal = _repo_less_cwd_refusal(payload)
    if refusal:
        _write_bytes(sys.stdout, json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": refusal,
        }}) + "\n")
        return 0

    skipped: List[str] = []
    trailing_stderr: List[str] = []
    contexts: List[str] = []
    system_messages: List[str] = []
    upstream_input: Optional[dict] = None

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
    advisory = _skill_stage_advisory(payload)
    if advisory:
        contexts.append(advisory)

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
