#!/usr/bin/env python3
"""PreToolUse(Bash) naked-Python dispatcher.

Replaces the former ~11-script bash dispatcher (which itself folded the
no-verify, destructive-git-orphan, destructive-rm, destructive-git-clean,
destructive-git-revert, blanket-git-add, runaway-find, git-c-over-cd, and
probe-spray guards, plus commit validation) PLUS the 5-fold
subagent-identity cohort (subagent-plan-body-bash-write,
reviewer-bash-outside-allowlist, subagent-destructive-action,
subagent-scoped-commit, illegal-filename
Bash leg) with ONE `python3` PreToolUse(Bash) registration — zero Git-Bash
cold-starts per Bash tool call (each bash.exe spawn costs 200-500ms on
Windows; this is the whole point, mirroring `preuse-write-dispatch.py`'s
rationale for the Write/Edit/MultiEdit/NotebookEdit side).

DoE owns only this thin PLUMBING shim (DR-047 transport-seam carve-out):
resolve the claude-klabauter engine, hand it the raw payload, relay its stdout. Claude-klabauter
owns the guard LOGIC (`coordinator_core.bash_guards.dispatch`, which reuses
`coordinator_core.bash_guards.*` and `coordinator_core.subagent_sandbox`).
The engine is imported and run IN-PROCESS — no bash, no `python3 -m`
subprocess re-spawn — so a whole Bash tool call pays exactly one Python
interpreter start.

Contract (mirrors the bash dispatcher it replaces):
  stdin   — PreToolUse JSON (tool_name, tool_input.command, session_id, cwd,
            agent_id…)
  stdout  — one nested hookSpecificOutput JSON envelope on deny/rewrite/
            advisory; NOTHING on allow
  exit 0  — always (ALLOW/DENY conveyed via stdout, never exit code)

Graceful degradation — REQUIRED: any failure to resolve/import/run the
Claude-klabauter engine falls through to fail-open ALLOW (exit 0, no stdout). A
missing sibling engine must NEVER brick every Bash tool call — identical
philosophy to `preuse-write-dispatch.py`'s claude-klabauter-resolution fallback.

The bash-to-Python cutover is complete; this dispatcher is the sole
PreToolUse(Bash) registration in hooks.json.

Spec backlink: scratch/subagent-sandbox/bash-to-python-migration/
W3a-preuse-bash-recipe.md Sec(c)

Policy-path injection (C5a, 2026-07-27): every resolution leg inside
Claude-klabauter's ``engine.load_policy()`` -- explicit path -> ``SUBAGENT_SANDBOX_
POLICY`` env (set by no code in either repo) -> ``_resolve_default_policy_
path()``, which that module's own docstring calls "deliberately weak" --
fail-opens to an empty ``Policy`` unless a caller hands it an explicit path.
This dispatcher computes that path the same way
``enforce-agent-dispatch-mode.py`` already does for its own subprocess call
(``Path(__file__).resolve().parents[2] / "subagent-sandbox-policy.yaml"``)
and passes it to ``evaluate_payload_json`` as an explicit ``policy_file``
keyword -- the in-process equivalent of that other script's ``--policy
<policy_file>`` subprocess flag -- rather than leaving resolution to the
weak in-process fallback chain. Precedent on record:
cross-repo/archive/2026-07-25-claude-klabauter-em-code-reviewer-sidecar-provisioning-fails-most-spawns.md
documents this exact mechanism silently fail-opening on 4 of 5 spawns in
production.

``evaluate_payload_json`` does not accept ``policy_file`` yet as of this
commit -- that signature change is a separate claude-klabauter-side chunk (C6). This
call site feature-detects via ``inspect.signature`` and only passes the
keyword once the callee declares it, so behavior is byte-for-byte identical
to today until C6 lands, and starts flowing the explicit path automatically
the moment it does -- no further edit to this file required.

Resolution-class injection (2026-08-05): this dispatcher resolves the engine
via ``resolve_claude_klabauter_root_with_class`` and forwards the class alongside the
root, under the same feature-detect idiom as ``policy_file`` above.

Why it matters here specifically, rather than as diagnostics: a consumer
executing a half-written engine mid-edit sees a guard behaving oddly, a Bash
call wrongly denied, or an op erroring -- none of which is distinguishable,
from this seat, from that engine behaving correctly. That is the half of the
defect ``_engine_root.resolve_claude_klabauter_root_with_class`` calls
silent-by-construction, and it cost a sibling plane two days on a wrong
theory. Calling the class-dropping ``resolve_claude_klabauter_root`` wrapper here threw
the answer away at the one seam best placed to report it.

This shim resolves and forwards; the engine plane decides what to render,
since the guard MESSAGE is engine-owned under the same DR-047 split as the
guard logic. Until ``evaluate_payload_json`` declares ``resolution_class``,
the keyword is not passed and behavior is byte-for-byte identical to today.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        arm_lazy_ops as _arm_lazy_ops,
        resolve_claude_klabauter_root_with_class as _resolve_engine,
    )
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    # "unresolved" is spelled literally rather than imported as
    # RESOLUTION_UNRESOLVED: this leg exists precisely for the case where
    # that module is absent, so it cannot depend on a name from it.
    def _resolve_engine() -> tuple[str | None, str]:
        return None, "unresolved"

    def _arm_lazy_ops() -> None:
        return None


def main() -> int:
    # SECURITY BOUNDARY, not only a cold-start optimization: this function
    # runs as a FRESH subprocess per PreToolUse(Bash) event, reads the
    # candidate command from stdin as inert text, and never shell-execs it
    # -- so no COORDINATOR_OVERRIDE_*/COORDINATOR_ALLOW_* env var a subagent
    # tries to set via an inline `VAR=1` prefix, `export`, or `env` wrapper
    # inside the candidate command can ever reach this process's
    # os.environ, which is the only thing `dispatch_checks._override()`
    # reads. Pooling/reusing this process across events to cut the
    # per-call spawn cost would silently delete that guarantee. Pinned in two
    # halves, in two repos, because a pooling change can be made from either
    # side: the behavioural half by
    # coordinator_core/bash_guards/tests/test_override_unreachability_boundary.py
    # (claude-klabauter), and the registration half -- that hooks.json keeps
    # this wired as a per-event `type: "command"` hook -- by
    # coordinator/tests/test_bash_guard_hook_stays_per_event.py (here).
    # Do not "fix" either test's failure by deleting it; re-key the affected
    # confinement guards onto resolved caller-context first.
    raw = sys.stdin.read()

    root, resolution_class = _resolve_engine()
    if not root:
        return 0  # fail-open ALLOW — engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    # Must precede the first coordinator_core.* import -- see
    # _engine_root.arm_lazy_ops for the ~80ms package-init cost this avoids.
    # This dispatcher is the hottest hook stub in the system: one fresh
    # subprocess per PreToolUse(Bash) event.
    _arm_lazy_ops()

    try:
        from coordinator_core.bash_guards.dispatch import evaluate_payload_json
    except Exception:
        return 0  # engine unimportable → fail-open ALLOW

    # __file__ parents: [0]=scripts [1]=hooks [2]=coordinator(plugin root) --
    # same depth as enforce-agent-dispatch-mode.py's identical computation,
    # since both scripts live in this same directory.
    policy_file = Path(__file__).resolve().parents[2] / "subagent-sandbox-policy.yaml"

    try:
        _params = inspect.signature(evaluate_payload_json).parameters
        accepts_policy_file = "policy_file" in _params
        accepts_resolution_class = "resolution_class" in _params
    except (TypeError, ValueError):
        accepts_policy_file = False
        accepts_resolution_class = False

    kwargs = {}
    if accepts_policy_file:
        kwargs["policy_file"] = str(policy_file)
    if accepts_resolution_class:
        kwargs["resolution_class"] = resolution_class

    try:
        out = evaluate_payload_json(raw, **kwargs)
    except Exception:
        return 0  # any engine failure → fail-open ALLOW (never brick a Bash call)

    if out is not None:
        import json

        sys.stdout.write(json.dumps(out))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
