#!/usr/bin/env python3
"""PreToolUse(Bash|PowerShell) fan-in dispatcher -- three hooks.json
`Bash|PowerShell`-matcher registrations, one interpreter
(state/audits/2026-08-16-doe-hook-consolidation-feasibility.md, this
dispatch's own fold: `guard-doctrine-surface-bash-write.py` and
`guard-repo-setup-claude-home-refusal.py` are folded IN, ahead of the
engine-backed dispatch this file already hosted, following the same
registry + dynamic-import + first-deny-wins shape `preuse-agent-dispatch.py`
already ships for the Agent-matcher leg of PreToolUse.

FOLD SHAPE -- FIRST-DENY-WINS, NOT CONCATENATE-ALL, mirroring
`preuse-agent-dispatch.py`'s own choice for the same reason: each of the two
folded guards is a hard exit-0/exit-2 refusal (never an advisory), so the
first one that denies is the whole verdict -- there is nothing for a second
guard's text to add once the command is already blocked. The two folded
guards run BEFORE the engine dispatch below (cheaper, DoE-resident, no
sibling-repo resolution), in their PRIOR hooks.json registration order
(`guard-doctrine-surface-bash-write.py` first, then
`guard-repo-setup-claude-home-refusal.py`) -- registration order was never
policy-significant between these two (their predicates are structurally
disjoint: one keys on a governed-doctrine-surface mention, the other on the
repo-setup scaffold mechanism naming Claude Home), so preserving it is a
convenience, not a behaviour dependency. Only once NEITHER denies does this
file's own engine-backed evaluation run, exactly as it did standalone.

LAZY SCOPE DESCRIPTORS. Each folded guard carries an import-FREE, string-only
precondition (`_pre_doctrine_surface`/`_pre_repo_setup`) computed from the
raw payload's `tool_name`/`tool_input.command` alone -- no module import, no
regex compilation, no `_claude_md_ledger`/wiki-anchor module load -- for the
overwhelming majority of Bash/PowerShell calls that mention no governed
identifier and no scaffold-mechanism marker at all. This is the same
"a guard's expensive work must not run when its precondition is false" shape
`stop-dispatch.py` ships for the Stop event; unlike that dispatcher's five
guards, here BOTH preconditions are payload-text-only (no filesystem stat,
no transcript read) since both folded guards' own predicates are themselves
payload-text-only.

FAILURE ISOLATION. Each of the two folded guards runs inside its own
`try/except BaseException`, with a stderr skipped-list breadcrumb on the
guard that raised -- one guard crashing removes only that guard's coverage
(fail-open for it alone) and the dispatcher proceeds to the next guard, then
to the engine dispatch, exactly as `stop-dispatch.py`/`preuse-agent-
dispatch.py` isolate their own folded guards. This is a NEW isolation layer,
not a narrowing of either guard's own contract: both guards already fail
open internally on a malformed payload or an uncatchable classification (see
each guard's own module docstring) -- this outer wrapper only catches a
genuinely unexpected crash in THIS file's own invocation plumbing (a bug in
`_import_guard`/`_invoke`, a malformed `sys.modules` entry), the same narrow
residual `preuse-agent-dispatch.py`'s own docstring names for its guards 1-3.

Original module purpose (still the majority of this file, unchanged below):
replaces the former ~11-script bash dispatcher (which itself folded the
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

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out):
resolve the engine repo, hand it the raw payload, relay its stdout. The engine
repo owns the guard LOGIC (`coordinator_core.bash_guards.dispatch`, which reuses
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
engine repo falls through to fail-open ALLOW (exit 0, no stdout). A
missing sibling engine must NEVER brick every Bash tool call — identical
philosophy to `preuse-write-dispatch.py`'s engine-resolution fallback.

The bash-to-Python cutover is complete; this dispatcher is the sole
PreToolUse(Bash) registration in hooks.json.

Spec backlink: scratch/subagent-sandbox/bash-to-python-migration/
W3a-preuse-bash-recipe.md Sec(c)

Policy-path injection (C5a, 2026-07-27): every resolution leg inside
the engine repo's ``engine.load_policy()`` -- explicit path -> ``SUBAGENT_SANDBOX_
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
commit -- that signature change is a separate engine-side chunk (C6). This
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

Provenance injection (2026-08-16, C2, F6/AC20): this dispatcher now resolves
via ``resolve_claude_klabauter_root_with_provenance`` (the three-value seam) and
forwards ``provenance`` alongside ``resolution_class``, under the SAME
``inspect.signature`` feature-detect idiom -- inert until the engine plane
declares the ``provenance`` keyword, same byte-for-byte-identical-until-then
guarantee as ``resolution_class`` and ``policy_file`` above. This is the
second observability surface for the provenance seam: the boot banner
(``project-orientation.py::engine_resolution_banner``) is per-*session*, so a
hook running under an inherited ``CLAUDE_KLABAUTER_ROOT``/``REPO_CLAUDE_KLABAUTER``
override in an unrelated repo renders no banner at all -- but the override
still leaks per-*process* through ``child_env()`` to every subprocess this
dispatcher's engine call spawns, and THAT leak is what this per-call
forwarding makes observable to the engine plane.
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        arm_lazy_ops as _arm_lazy_ops,
        resolve_claude_klabauter_root_with_provenance as _resolve_engine,
    )
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    # "unresolved" is spelled literally rather than imported as
    # RESOLUTION_UNRESOLVED: this leg exists precisely for the case where
    # that module is absent, so it cannot depend on a name from it.
    def _resolve_engine() -> tuple[str | None, str, str]:
        return None, "unresolved", "none"

    def _arm_lazy_ops() -> None:
        return None


def _rearm_command_tool_name(raw: str) -> str:
    """Re-arm of the engine repo's command-guard chain under the PowerShell tool.

    All 22 gates in ``coordinator_core.bash_guards`` test ``tool_name == "Bash"`` --
    the dispatcher itself plus each guard's own ``check(payload)`` -- so on a
    Windows workstation with no Bash tool, every guard silently returns ``None``
    under the PowerShell tool while the test suite stays green (it calls guard
    functions directly, never through the harness matcher). This rewrites
    ``tool_name`` from ``"PowerShell"`` to ``"Bash"`` before the payload reaches
    ``evaluate_payload_json``, re-arming the chain from the one seam the doctrine plane owns,
    without waiting on the engine repo's unscheduled XL 22-site conversion.

    Proven mechanism, not a guess: see
    docs/research/spike-verdicts/2026-08-07-powershell-guard-chain-rearm-via-tool-name-normalization.md
    -- with normalization active, a real command issued through the PowerShell
    tool was observed BLOCKED by a guard; with the sentinel removed, the
    byte-identical command ran.

    ON BY DEFAULT since 2026-08-07 (DR-144). This shipped opt-in behind a
    session-keyed sentinel and was flipped to unconditional on PM ratification
    once roster evidence existed: 24 distinct guards were observed firing under
    the PowerShell tool with normalization active, 14 of the 20 severity-ranked
    roster items fully discharged, no regression to the Bash leg observed.
    Evidence: state/audits/2026-08-07-bx17-piece3-observed-block-discharge.md.
    Before the flip, guard coverage on a PowerShell-only workstation was ZERO
    by construction while the test suite stayed green -- that asymmetry, not
    the convenience, is what justified promoting it.

    NO SESSION-KEYED OPT-OUT, DELIBERATELY -- and this is a negative spec, not
    an omission. A session-keyed opt-out sentinel was written during the flip
    and removed before it landed: under an opt-IN default, a sentinel an agent
    could create only ever *armed* guards, so agent-writability was harmless.
    Inverted to opt-OUT, the identical file becomes a one-line chain-wide
    self-disarm that any agent can write for itself, defeating every guard in
    ``bash_guards`` at once. The engine repo already treats that shape as hostile --
    ``block_disarm_marker_sentinel_creation`` exists precisely to stop an agent
    creating a blanket-disarm marker -- so shipping an unguarded equivalent
    here would have punched a hole through a boundary the sibling plane
    actively defends. Do not re-add one.

    The escape hatches that already exist are the right ones, and they are
    operator-facing rather than agent-facing: each guard advertises its own
    one-shot ``coordinator-guard-unlock-<session_id>.<guard>`` key in its own
    deny message, and each carries a pre-launch ``COORDINATOR_OVERRIDE_*`` env
    var. Per-guard and human-gated beats chain-wide and agent-writable.

    Checks run cheapest-first (AC-3), because this is the hottest hook path in
    the system -- one fresh subprocess per command tool call:
      1. empty ``raw`` -> return unchanged.
      2. parse JSON; non-dict -> return unchanged.
      3. ``tool_name`` not in ``("PowerShell",)`` -> return unchanged. This is
         the fast path for every ordinary Bash call, and it touches no
         filesystem at all -- there is no sentinel stat() left on any path.
      4. otherwise set ``payload["tool_name"] = "Bash"`` and return
         ``json.dumps(payload)``.
    The whole body is wrapped in ``try/except Exception: return raw`` --
    fail-open is the contract, not a nicety, since this function sits in front
    of every command tool call in every session sharing the worktree (AC-3).
    ``session_id`` is no longer read here; a malformed one can no longer
    suppress the rewrite, which is the one behavioural inversion the flip
    introduces beyond the default itself.

    RETIREMENT CONDITION (AC-5): this is a placeholder for the engine repo's SSOT
    command-tool constant, where guards test MEMBERSHIP in a tool set rather
    than equality with one literal name. Delete this function -- and its call
    site in ``main()`` -- the moment that constant lands and
    ``evaluate_payload_json`` (or its dispatcher) consumes it.

    REVIEW TRIGGER -- 2026-11-07, or sooner if the engine repo's constant lands
    first. A dated trigger rather than a bare "retire me eventually", because
    the named risk in ratifying this flip was precisely that a placeholder
    which works well enough never gets retired. If that date passes with the
    constant still unbuilt, the question to put to the PM is whether to chase
    the engine repo's conversion or accept this as the permanent seam -- not
    whether to leave it undecided for another quarter.
    """
    try:
        import json

        if not raw:
            return raw

        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return raw

        if payload.get("tool_name") not in ("PowerShell",):
            return raw

        payload["tool_name"] = "Bash"
        return json.dumps(payload)
    except Exception:
        return raw


# --------------------------------------------------------------------------
# Fold: guard-doctrine-surface-bash-write.py + guard-repo-setup-claude-home-
# refusal.py, first-deny-wins, ahead of the engine dispatch below. See module
# docstring "FOLD SHAPE" / "LAZY SCOPE DESCRIPTORS" / "FAILURE ISOLATION".
# --------------------------------------------------------------------------

_COMMAND_TOOL_NAMES = ("Bash", "PowerShell")


def _extract_command_for_preconditions(raw: str) -> "Tuple[Optional[str], Optional[str]]":
    """Best-effort, side-effect-free ``(tool_name, command)`` extraction from
    the raw stdin payload -- used ONLY to compute the two folded guards'
    lazy-import preconditions below. Never raises; any parse failure yields
    ``(None, None)``, which simply skips both guards' import -- matching
    what each guard's own ``main()`` would independently decide (fail open)
    on the identical malformed input, so skipping the import here changes no
    observable behaviour."""
    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            return None, None
        tool_name = payload.get("tool_name")
        tool_input = payload.get("tool_input")
        cmd = tool_input.get("command") if isinstance(tool_input, dict) else None
        return (
            tool_name if isinstance(tool_name, str) else None,
            cmd if isinstance(cmd, str) else None,
        )
    except Exception:
        return None, None


def _pre_doctrine_surface(tool_name: "Optional[str]", cmd: "Optional[str]") -> bool:
    if tool_name not in _COMMAND_TOOL_NAMES or not cmd:
        return False
    try:
        from _claude_md_ledger import GOVERNED_AUTHORING_SURFACES
    except Exception:
        # Cannot cheaply prefilter without the ledger module -- import the
        # guard itself and let IT decide, rather than silently skipping a
        # command this precondition could not classify.
        return True
    lowered = cmd.lower()
    for surface in GOVERNED_AUTHORING_SURFACES:
        if surface.lower() in lowered or surface.rsplit("/", 1)[-1].lower() in lowered:
            return True
    return False


def _pre_repo_setup(tool_name: "Optional[str]", cmd: "Optional[str]") -> bool:
    if tool_name not in _COMMAND_TOOL_NAMES or not cmd:
        return False
    return "repo-setup-args-and-register" in cmd or "scaffold_structure" in cmd


@dataclass(frozen=True)
class _BashGuard:
    module_key: str
    filename: str
    precondition: Callable[["Optional[str]", "Optional[str]"], bool]


# Prior hooks.json registration order -- see module docstring "FOLD SHAPE"
# for why preserving it is a convenience, not a behaviour dependency.
_BASH_GUARD_REGISTRY: "Tuple[_BashGuard, ...]" = (
    _BashGuard("guard_doctrine_surface_bash_write", "guard-doctrine-surface-bash-write.py",
               _pre_doctrine_surface),
    _BashGuard("guard_repo_setup_claude_home_refusal", "guard-repo-setup-claude-home-refusal.py",
               _pre_repo_setup),
)


class _ByteSink:
    """Binary-mode facade for `_BufferedTextCapture.buffer`: writes bytes straight
    through, UNMODIFIED, into the SAME ordered `io.BytesIO` the text channel's
    `write(str)` encodes into -- no decode, no round-trip at capture time. Both
    folded guards here write their deny message via `sys.stderr.buffer.write()`
    (Windows CRLF-translation fix -- see each guard's own module docstring, and
    `_stop_family_runner.py`'s `_ByteSink` docstring for the full rationale). This
    dispatcher's own re-emission (below) writes `.encode("utf-8")` through
    `sys.stderr.buffer`, never the text wrapper, so that guarantee survives the
    round trip to the real process stderr."""

    def __init__(self, sink: "io.BytesIO") -> None:
        self._sink = sink

    def write(self, data: bytes) -> int:
        return self._sink.write(data)

    def flush(self) -> None:
        pass


class _BufferedTextCapture(io.StringIO):
    """Same shim `stop-dispatch.py`/`preuse-agent-dispatch.py` use: both
    folded guards write their deny message via `sys.stderr.buffer.write()`
    (Windows CRLF-translation fix -- see each guard's own module docstring),
    which a plain `io.StringIO` has no `.buffer` attribute for. Both channels
    land in ONE ordered `io.BytesIO` -- `write(str)` encodes into it,
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


def _import_bash_guard(guard: "_BashGuard") -> Any:
    if guard.module_key in sys.modules:
        return sys.modules[guard.module_key]
    spec = importlib.util.spec_from_file_location(
        guard.module_key, str(Path(_HOOKS_DIR) / guard.filename)
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


def _invoke_bash_guard(main_fn: Callable[[], int], stdin_text: str) -> "Tuple[int, str]":
    old_stdin = sys.stdin
    err_buf = _BufferedTextCapture()
    rc = 0
    with contextlib.redirect_stderr(err_buf):
        sys.stdin = io.StringIO(stdin_text)
        try:
            try:
                rc = main_fn()
            except SystemExit as exc:
                rc = exc.code if isinstance(exc.code, int) else 0
        finally:
            sys.stdin = old_stdin
    return (rc or 0), err_buf.combined()


def _run_folded_bash_guards(raw: str) -> "Optional[int]":
    """Runs the two folded guards, first-deny-wins. Returns 2 (already having
    written the denying guard's stderr) the moment one denies; returns
    ``None`` once neither denies (or both were skipped/crashed), signalling
    the caller to fall through to the engine dispatch."""
    tool_name, cmd = _extract_command_for_preconditions(raw)
    skipped: "List[str]" = []

    for guard in _BASH_GUARD_REGISTRY:
        try:
            if not guard.precondition(tool_name, cmd):
                continue
        except BaseException:
            skipped.append(guard.module_key + " (precondition)")
            continue
        try:
            mod = _import_bash_guard(guard)
            rc, err = _invoke_bash_guard(mod.main, raw)
        except BaseException:
            skipped.append(guard.module_key)
            continue
        if rc == 2:
            if skipped:
                sys.stderr.write(
                    "[preuse-bash-dispatch] guard(s) skipped (fail-open for "
                    "those only): " + ", ".join(skipped) + "\n"
                )
            if err:
                # Re-emit through .buffer, never the text wrapper -- err came
                # from _BufferedTextCapture.combined(), which may carry a
                # guard's raw sys.stderr.buffer.write() bytes (Windows
                # CRLF-translation fix); a text-mode write here would
                # reintroduce exactly the translation that convention exists
                # to avoid. See _ByteSink's own docstring above.
                sys.stderr.buffer.write(err.encode("utf-8"))
                sys.stderr.buffer.flush()
            return 2

    if skipped:
        sys.stderr.write(
            "[preuse-bash-dispatch] guard(s) skipped (fail-open for those "
            "only): " + ", ".join(skipped) + "\n"
        )
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
    # (the engine repo), and the registration half -- that hooks.json keeps
    # this wired as a per-event `type: "command"` hook -- by
    # coordinator/tests/test_bash_guard_hook_stays_per_event.py (here).
    # Do not "fix" either test's failure by deleting it; re-key the affected
    # confinement guards onto resolved caller-context first.
    raw = sys.stdin.read()

    # Folded guards run on the ORIGINAL payload, before the PowerShell->Bash
    # rearm below -- both already accept tool_name in ("Bash", "PowerShell")
    # natively, so rearming first would only be a no-op relabel, not a
    # behaviour change; keeping them on the untouched payload is the more
    # conservative choice. First-deny-wins: a 2 here is the whole verdict.
    folded_rc = _run_folded_bash_guards(raw)
    if folded_rc is not None:
        return folded_rc

    raw = _rearm_command_tool_name(raw)

    root, resolution_class, provenance = _resolve_engine()
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
        accepts_provenance = "provenance" in _params
    except (TypeError, ValueError):
        accepts_policy_file = False
        accepts_resolution_class = False
        accepts_provenance = False

    kwargs = {}
    if accepts_policy_file:
        kwargs["policy_file"] = str(policy_file)
    if accepts_resolution_class:
        kwargs["resolution_class"] = resolution_class
    if accepts_provenance:
        kwargs["provenance"] = provenance

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
