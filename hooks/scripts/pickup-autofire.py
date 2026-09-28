#!/usr/bin/env python3
"""UserPromptExpansion auto-fire hook for baton grabs (naked Python, no bash).

Purpose: when the EM (or a peer session) types `/pickup <artifact-path>`, this
hook fires ahead of `UserPromptSubmit`, computes the pickup decision object via
the engine-side `pickup-assemble brief` CLI, and injects a rendered summary as
`additionalContext` — so the brief already exists by the time the EM's own
turn starts acting on the command. When the computed decision reads
`coast: clear` with zero unresolved `judgment_points`, the hook ALSO fires the
mutating `pickup-assemble apply` half, propagating the event payload's own
`session_id` explicitly (never relying on ambient tier-4 sentinel resolution
downstream — see `_apply_argv`'s docstring).

The same firing covers an autonomous-run command handed batons on its argument
line. Handing batons to a run IS a grab — the claim is what stops a concurrent
session from picking up the same handoff mid-run, and a run coordinating its
own executors by file-disjointness has no other cross-session guarantee. So the
run's batons brief, claim, and render through this identical path rather than
through a doctrine step the operator has to remember; the only extra work is
filtering the baton paths out of a mixed argument string that also carries
flags, item identifiers, and plan paths (`extract_baton_paths`). Naming no
baton passes silently, leaving an ordinary backlog run untouched.

Contract (mirrors the sibling hooks in this directory):
  stdin   -- UserPromptExpansion JSON (command_name, command_args,
             command_source, cwd, expansion_type, session_id, prompt_id, ...)
  stdout  -- one `hookSpecificOutput` JSON envelope with `additionalContext`
             when a `pickup`-verb command was matched and a brief could be
             computed; NOTHING otherwise (silent pass — a non-pickup command,
             or a total transport failure, produces no output)
  exit 0  -- always. This hook is advisory/mutating-via-a-vetted-CLI, never a
             blocking gate on the EM's own prompt — see AC9(c) below.

Spec: docs/plans/2026-07-23-computed-skills-bz-pickup-rebuild.md, chunk C3;
AC4, AC9, AC9(a-d), AC11, AC11b. Contract doc:
coordinator/docs/wiki/skills-corpus/computed-skills.md (decision-object JSON schema).

Safety envelope (AC9), each clause load-bearing:
  (a) SESSION-ID PROPAGATION, not event filtering. The event payload already
      carries its own originating `session_id` — there is no "foreign
      session" to filter once `command_name` matches a pickup verb (a foreign
      session's prompt cannot match unless that session itself typed it, in
      which case firing is correct). The hazard is downstream: `apply()`
      resolves claiming identity ambiently via `core.resolve_session_id`
      unless told otherwise, and that ambient path returns empty or an
      unrelated id under concurrency ambiguity. This hook passes the
      payload's `session_id` explicitly via `--session-id` (never relies on
      the ambient path) — see `_apply_argv`.
  (b) An absent or unrecognized `coast` verdict reads as HOLD, never as
      permission — see `_coast_verdict`/`_should_apply` (an older engine
      emitting no verdict must never be read as "clear").
  (c) Hook errors / timeouts / transport failures degrade to compute-only
      (or total silence, if even the brief could not be computed) and NEVER
      block `/pickup` — every subprocess call and every JSON decode in this
      module is wrapped to fail open, and `main()` never raises.
  (d) `additionalContext` never exceeds `_CONTEXT_BUDGET_CHARS` (10,000).
      Over-budget degrades per the rendering priority list `narration ->
      verdict -> next_move -> your_call -> pointer -> evidence`, dropped from
      the tail (evidence first, then the pointer line) — `next_move` and
      `your_call` (C4b) are never dropped, only the narration text is
      hard-truncated as a last resort. See `render_additional_context`.
      # Review: code-reviewer — module docstring's AC9(d) summary was
      # unchanged when C4b promoted `your_call` to a protected segment;
      # `render_additional_context`'s own docstring already documented it.

Never overrides a denied claim — there is no override code path in this
module at all; `_should_apply` only returns True on `coast: clear`, which
`compute_coast` (engine-side) never reports when `claim_grant.verdict ==
"denied"` (a denied claim always reads `coast: blocked`).

Install-surface note (recorded, not discovered at dogfood): the spike found
that a newly-registered `UserPromptExpansion` hook required `/reload-plugins`
before it started firing — a plain hooks.json edit alone was not enough (that
distinguishes it from other hook types the spike also touched, whose config
hot-reloaded without a restart).

Skill-tool-firing measurement (the Staff Engineer second-pass finding #9, same
instrumentation pass, near-zero marginal cost): `_log_probe_event` appends one
JSON line per hook firing (regardless of command match) to a tempfile-backed
log, recording `command_source`/`expansion_type`/`hook_event_name` alongside
`command_name` and `session_id`. The question this log was built to answer is
SETTLED: a `Skill`-tool (programmatic, EM-initiated) invocation does NOT fire
`UserPromptExpansion` at all (census row 2, docs/plans/2026-09-11-computed-
skill-inputs-reach-skill-tool-entry.md) — a typed `/pickup <path>` wrote one
line (`coordinator:pickup`, `slash_command`); the Skill-tool call wrote none.
That is exactly why this hook now also reads a second entry path
(`PreToolUse` on the `Skill` tool, via `compute_context`/`_skill_invocation`)
rather than relying on `UserPromptExpansion` alone. The log is retained, not
deleted, as the standing diagnostic surface the
`AN-AUTOFIRE-HOOK-THAT-DID-NOT-FIRE-IS-SILENT` tripwire
(coordinator/docs/wiki/coordinator-tripwires/an-autofire-hook-that-did-not-
fire-is-silent.md) tells operators to read — for verbs one of this hook's
own legs matches; a Skill call naming a verb no leg matches never reaches
this hook at all (C5's pre-gate filters it upstream), so the log's coverage
is scoped to matched verbs only.

Cross-repo consumer contract (negative-spec, closes the discharge-test gap
flagged in review): this hook is a HARD consumer of the engine repo's
`pickup-assemble brief`/`apply` CLI's output shape, pinned as of the engine
repo's commit `67828ff1` and the `main()` branch at
`coordinator_core/pickup_assemble/__init__.py:3868-3886` that emits it:
  - **N==1** grab → the CLI prints a BARE decision object (`{...}`), never a
    wrapped envelope.
  - **N>1** grab (an ` AND `-joined multi-artifact command) → the CLI prints
    a BARE JSON array of decision objects (`[{...}, {...}, ...]`) — NOT a
    `{"briefs": [...]}`-wrapped dict, and not any other envelope shape. A
    wrapped dict is a bare object as far as this hook's decoder is
    concerned (DEC-2) and is treated as ONE (almost certainly malformed)
    baton, never silently unwrapped into its `briefs` elements — there is
    no such unwrapping code path anywhere in this module.
  - **Process exit code** = the worst (max) per-artifact exit across the
    whole payload — this hook does not itself compute or re-derive that
    number; it only decodes whatever JSON the CLI already emitted to
    stdout.
A future engine-side change to this shape (e.g. switching to a wrapper
envelope) breaks this hook silently (fail-open swallows the parse failure
into "no output") unless a round-trip contract fixture on the engine side
also pins it — see chunk C7's cross-repo ask.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PureWindowsPath

# --- C3 producer-capture engine-import seam (docs/plans/2026-08-12-producer-
# axis-on-the-baton-contract.md D1/D3/D6) -------------------------------------
#
# `_engine_root.py` is the one seam every hook in this directory imports from
# to reach `coordinator_core` (see its own module docstring) -- reused here
# rather than re-deriving a second root-resolution ladder. Producer capture
# calls `coordinator_core.session.shape.producer_set` directly (a plain
# library function, not a registered `coordinator_core.hooks` advisory op),
# so it does not need the `ipc.dispatch_message` JSON-RPC indirection the
# sibling hooks in this directory use for their own bookkeeping ops.
_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    def _resolve_claude_klabauter_root() -> str | None:
        return None

from _skill_invocation import (  # noqa: E402
    context_envelope,
    read_invocation,
)

try:
    from _forwarder_resolve import forwarder_argv as _forwarder_argv  # noqa: E402
    from _forwarder_resolve import resolve_forwarder as _resolve_forwarder  # noqa: E402
except Exception:
    def _resolve_forwarder(bin_dir, name):  # type: ignore[misc]
        candidate = bin_dir / name
        return candidate if candidate.is_file() else None

    def _forwarder_argv(script_path, tail=()):  # type: ignore[misc]
        raise OSError("forwarder resolution unavailable -- import fallback declined to guess a launch decision")


_PICKUP_COMMAND_NAMES = frozenset({"pickup"})

# Commands that take batons among OTHER arguments. `/pickup`'s entire argument
# string is a path string; the wide run's is not (it also carries tail-mode
# flags and PM-named item identifiers), so its baton paths are extracted by
# family before anything reaches `pickup-assemble` -- see
# `extract_baton_paths`. Everything downstream of that extraction is shared:
# handing batons to a run IS a grab, so it briefs, claims, and renders through
# exactly the same path `/pickup` uses. There is deliberately no second claim
# mechanism for the mise surface.
#
# Both members name ONE ceremony (`commands/warp-speed-execute.md` forwards to
# `commands/mise-en-place.md`), so both must claim. This set is invocation
# vocabulary only -- it is matched against `command_name` and against nothing
# else. Kept literally identical to `mise-autofire.py :: _MISE_COMMAND_NAMES`;
# a verb in one and not the other starts the run half-wired, silently.
_BATON_GRAB_COMMAND_NAMES = frozenset({"mise-en-place", "warp-speed-execute"})

_BATON_PATH_FAMILIES = (
    "state/handoffs/",
    "archive/handoffs/",
    "state/cross-repo/inbox/",
    "state/cross-repo/archive/",
    "cross-repo/inbox/",
    "cross-repo/archive/",
)


_CONTEXT_BUDGET_CHARS = 10_000

_PROSE_SPLIT_RE = re.compile(r"\s+--\s+|\s+--$")


def split_prose_tail(command_args: str) -> tuple[str, str | None]:
    """Split `command_args` into `(path_string, prose_or_None)` on the FIRST
    match of `_PROSE_SPLIT_RE` (DEC-1). The left side is the AND-joined path
    string later handed to `pickup-assemble brief` UNCHANGED; the right side
    is free-text prose rendered as an EM-facing note and never sent to the
    engine repo. Absent a match, returns `(command_args, None)` — byte-identical
    to today's single-string path (AC4's "path resolution is byte-identical
    with vs. without the tail").

    Prose-strip happens BEFORE any ` AND ` splitting (that split is
    engine-side, via `split_artifact_args`), so prose text may itself
    contain ` AND ` harmlessly — it is isolated on this side of the ` -- `
    delimiter before the engine repo ever sees the path string.
    """
    parts = _PROSE_SPLIT_RE.split(command_args, maxsplit=1)
    if len(parts) == 2:
        left, right = parts
        prose = right.strip()
        return left.strip(), (prose if prose else None)
    return command_args, None

_AND_SPLIT_RE = re.compile(r"\s+AND\s+", flags=re.IGNORECASE)


def _is_baton_path(token: str) -> bool:
    normalized = PureWindowsPath(token).as_posix()
    return any(family in normalized for family in _BATON_PATH_FAMILIES)


def extract_baton_paths(command_args: str) -> str:
    """Extract the baton paths from a MIXED argument string, re-joined with
    ` AND ` for `pickup-assemble brief`.

    An autonomous-run command accepts batons alongside things that are not
    batons — a tail-mode flag, PM-named item identifiers, plan paths that are
    inventory input rather than artifacts with a claim. Briefing those would at
    best emit error batons and at worst make every ordinary invocation carry
    assembler noise, so only `_BATON_PATH_FAMILIES` members survive extraction.
    Returns `""` when the arguments name no baton at all — the caller reads
    that as "not a baton grab" and passes silently, which is what keeps a plain
    backlog run untouched by this hook.

    Negative-spec: never used on the `/pickup` path. There, the whole argument
    string is already a path string and is forwarded byte-identically (AC4);
    routing it through this filter would silently drop any artifact family not
    enumerated here, converting an assembler-side classification error into an
    invisible no-op.
    """
    tokens: list[str] = []
    for chunk in _AND_SPLIT_RE.split(command_args):
        tokens.extend(chunk.split())
    return " AND ".join(token for token in tokens if _is_baton_path(token))


_BRIEF_TIMEOUT_SECONDS = 12
_APPLY_TIMEOUT_SECONDS = 20

# Windows console-subprocess discipline: `python.exe` is a CONSOLE-subsystem
# child. `getattr` resolves to 0 (no-op) on every non-Windows platform.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_PROBE_LOG_NAME = "pickup-autofire-events.jsonl"
_PROBE_LOG_PATH_ENV = "PICKUP_AUTOFIRE_PROBE_LOG_PATH"


# --- COORDINATOR_SETTINGS_HOME resolution (AC11b) ---------------------------


def resolve_settings_home() -> Path:
    """Resolve the coordinator-claude settings-home root.

    Precedence (AC11b): an explicit `COORDINATOR_SETTINGS_HOME` override is
    used AS-IS (it already points AT the settings home); otherwise
    `CLAUDE_HOME` (or `HOME`) joined with the fixed `.coordinator-claude-
    settings` suffix. Mirrors `_engine_root.py::_settings_home_registry_dir`'s
    documented precedence bit-for-bit (that module resolves one level deeper,
    into `machine-local/`; this one stops at the settings-home root itself,
    since `bin/` is a sibling of `machine-local/`, not nested under it).

    Negative-spec: never bareword `pickup-assemble` (COORDINATOR_SETTINGS_HOME
    is not on PATH), never a hardcoded absolute path, never `~/.claude`-only
    (that directory has never been the settings-home root on this fleet).
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


def resolve_pickup_assemble_bin(settings_home: Path) -> Path | None:
    return _resolve_forwarder(settings_home / "bin", "pickup-assemble")


def pickup_assemble_argv(script_path: Path, tail: list[str]) -> list[str]:
    return _forwarder_argv(script_path, tail)


class _TransportFailure(Exception):
    pass


def _run_pickup_assemble(
    script_path: Path, tail: list[str], session_id: str, timeout: float
) -> subprocess.CompletedProcess:
    """Run the resolved forwarder, propagating `session_id` into the child
    environment (`COORDINATOR_SESSION_ID`) as a belt-and-suspenders companion
    to the explicit `--session-id` argument the caller also passes on the
    `apply` path (AC9a) — `apply()` itself prefers the explicit argument, but
    setting the env var too costs nothing and covers any code path that only
    checks the env.

    Raises `_TransportFailure` on ANY failure to complete the subprocess
    (spawn error, timeout) — never lets a raw OSError/TimeoutExpired escape,
    since every caller of this function must be able to fail open (AC9c).
    """
    env = dict(os.environ)
    if session_id:
        env["COORDINATOR_SESSION_ID"] = session_id
    try:
        argv = pickup_assemble_argv(script_path, tail)
        return subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _TransportFailure(str(exc)) from exc


def decode_decision_payload(stdout: str) -> list[dict]:
    try:
        obj = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list):
        return [item for item in obj if isinstance(item, dict)]
    return []


def _stdout_is_well_formed(stdout: str) -> bool:
    try:
        obj = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(obj, (dict, list))


def _baton_grab_summary(decisions: list, spool_open_count: int, subagent: bool) -> str:
    claimed: list[str] = []
    if not subagent:
        for decision in decisions:
            if not isinstance(decision, dict) or not should_apply(decision):
                continue
            artifact = decision.get("artifact")
            path = artifact.get("path") if isinstance(artifact, dict) else None
            if isinstance(path, str) and path:
                claimed.append(path)
    return f"batons_claimed={claimed!r}, spool_open_count={spool_open_count}"


def coast_verdict(decision: dict) -> str | None:
    gates = decision.get("gates")
    if not isinstance(gates, dict):
        return None
    coast = gates.get("coast")
    if not isinstance(coast, dict):
        return None
    verdict = coast.get("verdict")
    return verdict if isinstance(verdict, str) else None


def judgment_points_are_empty(decision: dict) -> bool:
    jps = decision.get("judgment_points")
    return isinstance(jps, list) and len(jps) == 0


def should_apply(decision: dict) -> bool:
    return coast_verdict(decision) == "clear" and judgment_points_are_empty(decision)


def _unclaimed_summary(
    decisions: list, multi: bool, subagent_guard: bool = False
) -> str | None:
    lines = []
    for index, decision in enumerate(decisions):
        would_apply = should_apply(decision)
        if would_apply and not subagent_guard:
            continue
        if would_apply and subagent_guard:
            artifact = decision.get("artifact") if isinstance(decision, dict) else None
            name = (artifact or {}).get("path") if isinstance(artifact, dict) else None
            label = f"baton {index + 1}" if multi else "baton"
            lines.append(
                f"  - {name or label}: not claimed: a claim from a subagent's tool "
                "call is not the main session's deliberate grab, whatever "
                "session_id it carries"
            )
            continue
        gates = decision.get("gates") if isinstance(decision, dict) else None
        grant = (gates or {}).get("claim_grant") if isinstance(gates, dict) else None
        grant = grant if isinstance(grant, dict) else {}
        artifact = decision.get("artifact") if isinstance(decision, dict) else None
        name = (artifact or {}).get("path") if isinstance(artifact, dict) else None
        holder = grant.get("holder")
        reason = str(grant.get("reason") or "").strip()
        if holder and not grant.get("held_by_self"):
            live = "live" if grant.get("holder_live") else "not live in this box's registry"
            why = f"claimed by session {holder} ({live})"
        elif reason:
            why = reason
        else:
            why = "not claimable, and the brief carried no claim_grant reason to quote"
        label = f"baton {index + 1}" if multi else "baton"
        lines.append(f"  - {name or label}: {why}")
    if not lines:
        return None
    return "Briefed but NOT claimed by this run:\n" + "\n".join(lines)


def _resolve_repo_root() -> Path | None:
    try:
        cwd = Path.cwd()
    except OSError:
        return None
    try:
        for candidate in (cwd, *cwd.parents):
            if (candidate / ".git").exists():
                return candidate
    except OSError:
        return None
    return None


def _sanitize_for_filename(value: str) -> str:
    return value.replace("/", "__").replace("\\", "__")


def _session_decision_file_path(repo_root: Path, session_id: str, artifact_path: str) -> Path:
    name = f"{_sanitize_for_filename(session_id)}__{_sanitize_for_filename(artifact_path)}.json"
    return repo_root / ".git" / "coordinator-sessions" / "decisions" / name


def _write_decision_files(decisions: list[dict], session_id: str) -> list[Path]:
    repo_root = _resolve_repo_root()
    if repo_root is None:
        return []
    tag = session_id or "unknown-session"
    written: list[Path] = []
    try:
        for decision in decisions:
            artifact = decision.get("artifact")
            artifact_path = (
                (artifact or {}).get("path") if isinstance(artifact, dict) else None
            )
            if not (isinstance(artifact_path, str) and artifact_path):
                continue
            path = _session_decision_file_path(repo_root, tag, artifact_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(decision, indent=2, sort_keys=True), encoding="utf-8"
            )
            written.append(path)
    except OSError:
        return []
    return written


def _your_call_text(decision: dict) -> str | None:
    """C4b: render the guidance-bearing `judgment_points[].dispositions[]`
    entries (C4's `guidance` field, landed engine-side on `_KIND_DISPOSITIONS`)
    as a "Your call" prose block — one bullet per disposition that carries
    non-empty `value` + `guidance`. Dispositions with no `guidance` (e.g.
    `build_untrusted_gate_judgment_point` entries, or a pre-C4 decision
    object) contribute nothing here and are left for the evidence tail.
    Returns None when no judgment_point carries guidance-bearing dispositions,
    so a decision with none renders identically to pre-C4b (AC3-compatible).
    """
    jps = decision.get("judgment_points")
    if not isinstance(jps, list):
        return None
    lines: list[str] = []
    for jp in jps:
        if not isinstance(jp, dict):
            continue
        question = jp.get("question")
        question_prefix = f"{question} — " if isinstance(question, str) and question else ""
        dispositions = jp.get("dispositions")
        if not isinstance(dispositions, list):
            continue
        for disp in dispositions:
            if not isinstance(disp, dict):
                continue
            value = disp.get("value")
            guidance = disp.get("guidance")
            if not (isinstance(value, str) and value):
                continue
            if not (isinstance(guidance, str) and guidance):
                continue
            lines.append(f"- {question_prefix}`{value}`: {guidance}")
    if not lines:
        return None
    return "Your call:\n" + "\n".join(lines)


def _evidence_judgment_points(decision: dict) -> list | None:
    jps = decision.get("judgment_points")
    if not isinstance(jps, list):
        return jps
    trimmed = []
    for jp in jps:
        if not isinstance(jp, dict):
            trimmed.append(jp)
            continue
        dispositions = jp.get("dispositions")
        if not isinstance(dispositions, list):
            trimmed.append(jp)
            continue
        kept_dispositions = [
            disp
            for disp in dispositions
            if not (
                isinstance(disp, dict)
                and isinstance(disp.get("guidance"), str)
                and disp.get("guidance")
            )
        ]
        trimmed.append({**jp, "dispositions": kept_dispositions})
    return trimmed


def _evidence_is_informative(decision: dict) -> bool:
    jps = decision.get("judgment_points")
    if isinstance(jps, list) and jps:
        return True
    gates = decision.get("gates")
    if not isinstance(gates, dict):
        return bool(gates)
    if set(gates.keys()) - {"coast"}:
        return True
    coast = gates.get("coast")
    if isinstance(coast, dict):
        return bool(set(coast.keys()) - {"verdict"})
    return bool(coast)


def _decision_segments(
    decision: dict, index: int, multi: bool
) -> tuple[str | None, str, str | None, str | None, str | None]:
    """Compute `(narration_text, verdict_text, next_move_text,
    your_call_text, evidence_text)` for ONE decoded decision object. When
    `multi` is True (an N>1 payload), each non-None line is prefixed
    `[Baton {index+1}] ` so a merged multi-baton render stays attributable
    per-artifact; `multi` False (N==1) applies no prefix, which is what keeps
    this byte-identical to the pre-existing single-object segments (AC3) when
    no judgment_point carries guidance.

    `your_call_text` (C4b) is the promoted "Your call" prose block for this
    baton's guidance-bearing dispositions -- protected alongside `next_move`,
    never rendered as raw JSON, never dropped under budget pressure.

    `evidence_text` is `None` outright (never composed, not composed-then-
    dropped) when `_evidence_is_informative` says this decision's `gates`/
    `judgment_points` add nothing past the Verdict line -- see that
    function's docstring. This is orthogonal to the `_CONTEXT_BUDGET_CHARS`
    degrade ladder below: a genuinely informative Evidence tail is still
    fully droppable there under real budget pressure.
    """
    narration = decision.get("narration")
    narration_text = narration if isinstance(narration, str) and narration else None

    verdict = coast_verdict(decision)
    jps = decision.get("judgment_points")
    jp_count = len(jps) if isinstance(jps, list) else "?"
    verdict_text = f"Verdict: coast={verdict!r}, judgment_points={jp_count}"

    next_move = decision.get("next_move")
    next_move_text = (
        f"Next move: {next_move}" if isinstance(next_move, str) and next_move else None
    )

    your_call_text = _your_call_text(decision)

    evidence_text = None
    if _evidence_is_informative(decision):
        evidence_payload = {
            "gates": decision.get("gates"),
            "judgment_points": _evidence_judgment_points(decision),
        }
        try:
            evidence_text = "Evidence:\n" + json.dumps(evidence_payload, indent=2, sort_keys=True)
        except (TypeError, ValueError):
            evidence_text = None

    if multi:
        prefix = f"[Baton {index + 1}] "
        if narration_text:
            narration_text = prefix + narration_text
        verdict_text = prefix + verdict_text
        if next_move_text:
            next_move_text = prefix + next_move_text
        if your_call_text:
            your_call_text = prefix + your_call_text
        if evidence_text:
            evidence_text = prefix + evidence_text

    return narration_text, verdict_text, next_move_text, your_call_text, evidence_text


def render_additional_context(
    decisions: list[dict],
    pointer_paths: list[Path],
    prose: str | None = None,
    subagent_guard: bool = False,
) -> str:
    """Render the `additionalContext` string per the AC9(d)/AC14/AC15/DEC-4
    priority list, generalized to N decoded batons: an optional EM-facing
    prose note (DEC-1/AC4) first, then per-baton `narration -> verdict ->
    next_move -> your_call`, then the pointer line naming the engine-path
    decision file(s) the EM should edit, then per-baton evidence.

    `pointer_paths` (docs/plans/2026-08-07-pickup-hold-path-decision-file-
    has-no-pr.md, AC4) is the list `_write_decision_files` actually wrote --
    ZERO or more paths, never a single shared pointer file. N==1 (exactly
    one path) keeps the pre-existing "Full decision object: <path>" wording
    (AC7 -- only the underlying value moved from a tempfile to the engine
    path). N>1 (or N==0 written against N>1 decisions) names every written
    path on its own line so the EM is never pointed at a file `apply` will
    not read.

    `your_call` (C4b) is the promoted "Your call" prose block rendering each
    guidance-bearing `judgment_points[].dispositions[]` entry's `value` +
    `guidance` as prose -- protected alongside `next_move` (never JSON, never
    dropped under budget pressure), because it is the operator-facing content
    C4's guidance exists to deliver; the raw `judgment_points` JSON (minus the
    guidance already promoted here) stays in the droppable evidence tail.

    Degrades under the `_CONTEXT_BUDGET_CHARS` cap by dropping WHOLE
    segments from the tail first — ALL batons' evidence, then the pointer
    line — before touching any baton's narration/verdict/next_move/your_call
    or the prose note (DEC-4: tier-wide, never per-object). `next_move` and
    `your_call` are never dropped for any single baton. If the protected
    segments (prose + narration/verdict/next_move/your_call for every baton)
    alone still overflow, the narration slots — the most compressible
    segment — are hard-truncated round-robin across batons, never
    verdict/next_move/your_call/prose. If NO baton carries narration text to
    sacrifice at all, whole later-baton (verdict, next_move, your_call)
    triples are dropped from the tail instead, one baton at a time, before
    any raw character slice is applied -- this keeps `next_move`/`your_call`
    intact for every baton that survives the drop; only the earliest
    surviving baton's own segment is ever raw-sliced, and only when it alone
    still overflows the budget. For N==1 with no prose tail and no
    guidance-bearing judgment_points (`your_call_text` is None, contributing
    nothing to the join) this reduces to exactly the pre-existing
    single-object behavior (AC3): the same 3 non-empty protected segments in
    the same order, the same 2 tail-droppable segments, the same
    truncate-narration-only last resort.

    `subagent_guard`: forwarded to `_unclaimed_summary` -- when True, every
    baton that would otherwise have been claimed is named as unclaimed
    instead (a dispatched subagent's own tool call is never a claim), rather
    than being silently skipped as "already handled".
    """
    if not decisions:
        return ""

    multi = len(decisions) > 1
    prose_text = f"EM note: {prose}" if prose else None

    per_baton = [_decision_segments(d, i, multi) for i, d in enumerate(decisions)]

    protected: list[tuple[str, str | None]] = []
    if prose_text:
        protected.append(("prose", prose_text))
    unclaimed_text = _unclaimed_summary(decisions, multi, subagent_guard=subagent_guard)
    if unclaimed_text:
        protected.append(("unclaimed", unclaimed_text))
    baton_offset = len(protected)
    narration_slots: list[int] = []
    for narration_text, verdict_text, next_move_text, your_call_text, _ in per_baton:
        if narration_text is not None:
            narration_slots.append(len(protected))
        protected.append(("narration", narration_text))
        protected.append(("verdict", verdict_text))
        protected.append(("next_move", next_move_text))
        protected.append(("your_call", your_call_text))

    if not pointer_paths:
        pointer_text = None
    elif len(pointer_paths) == 1:
        pointer_text = f"Full decision object: {pointer_paths[0]}"
    else:
        listing = "\n".join(f"  - {p}" for p in pointer_paths)
        pointer_text = f"Full decision payload (N={len(pointer_paths)}):\n{listing}"

    droppable: list[tuple[str, str | None]] = []
    if pointer_text:
        droppable.append(("pointer", pointer_text))
    for _, _, _, _, evidence_text in per_baton:
        if evidence_text:
            droppable.append(("evidence", evidence_text))

    def _join(segs: list[tuple[str, str | None]]) -> str:
        return "\n\n".join(text for _, text in segs if text)

    kept = protected + droppable
    rendered = _join(kept)

    while len(rendered) > _CONTEXT_BUDGET_CHARS and len(kept) > len(protected):
        kept.pop()
        rendered = _join(kept)

    if len(rendered) > _CONTEXT_BUDGET_CHARS:
        kept = list(protected)
        if not narration_slots:
            num_batons = len(per_baton)
            for keep_count in range(num_batons, 0, -1):
                trial = protected[: baton_offset + keep_count * 4]
                trial_rendered = _join(trial)
                if len(trial_rendered) <= _CONTEXT_BUDGET_CHARS or keep_count == 1:
                    return trial_rendered[:_CONTEXT_BUDGET_CHARS]
            return _join(kept)[:_CONTEXT_BUDGET_CHARS]

        texts = {i: (kept[i][1] or "") for i in narration_slots}
        rest = _join([seg for j, seg in enumerate(kept) if j not in narration_slots])
        while True:
            live = [t for t in texts.values() if t]
            separator_slack = 2 * len(live) if rest else 0
            budget_for_narrations = max(
                _CONTEXT_BUDGET_CHARS - len(rest) - separator_slack, 0
            )
            if sum(len(t) for t in texts.values()) <= budget_for_narrations:
                break
            if not any(texts.values()):
                break
            longest = max(texts, key=lambda i: len(texts[i]))
            texts[longest] = texts[longest][:-1]

        for i in narration_slots:
            orig = kept[i][1] or ""
            truncated = texts[i]
            if truncated and len(truncated) < len(orig):
                truncated = truncated[:-1] + "…" if truncated else "…"
            kept[i] = (kept[i][0], truncated if truncated else None)
        rendered = _join(kept)

    return rendered[:_CONTEXT_BUDGET_CHARS]


def _probe_log_path() -> Path:
    """Resolve the probe-log path, honoring `_PROBE_LOG_PATH_ENV`.

    Review: code-reviewer — factored out so a caller (chiefly tests) can
    point the log at a `tempfile.TemporaryDirectory()`-scoped file via the
    env override, instead of sharing the one fixed OS-tempdir path every
    process on the machine writes to.
    """
    override = os.environ.get(_PROBE_LOG_PATH_ENV)
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / _PROBE_LOG_NAME


def _log_probe_event(payload: dict) -> None:
    """Best-effort, near-zero-marginal-cost instrumentation (the Staff Engineer
    second-pass finding #9): append one JSON line per hook firing recording
    `command_name`/`command_source`/`expansion_type`/`session_id`/
    `hook_event_name` to a tempfile-backed log, regardless of whether
    `command_name` matched a pickup verb. The Skill-tool-firing question this
    log was built to answer is now settled (see the module docstring's own
    "Skill-tool-firing measurement" section) -- it is retained as the
    standing `AN-AUTOFIRE-HOOK-THAT-DID-NOT-FIRE-IS-SILENT` diagnostic
    surface, answering "did the Skill path fire" alongside the typed one for
    every verb one of this hook's legs matches. Never raises; a logging
    failure is invisible to the rest of the hook.
    """
    try:
        command_name = payload.get("command_name")
        if command_name is None:
            # A PreToolUse(Skill) payload carries no `command_name` -- the verb
            # lives in `tool_input.skill`. Logging the raw key alone writes a
            # row that proves the Skill path fired but cannot say WHICH verb
            # fired it, which is half the question the
            # AN-AUTOFIRE-HOOK-THAT-DID-NOT-FIRE-IS-SILENT diagnostic is read
            # to answer. Observed live on 2026-09-11 (session 962ed128): a
            # Skill(coordinator:pickup) call logged `command_name: null`.
            tool_input = payload.get("tool_input")
            if isinstance(tool_input, dict):
                for key in ("skill", "command"):
                    value = tool_input.get(key)
                    if isinstance(value, str) and value:
                        command_name = value
                        break
        record = {
            "ts": time.time(),
            "command_name": command_name,
            "command_source": payload.get("command_source"),
            "expansion_type": payload.get("expansion_type"),
            "session_id": payload.get("session_id"),
            "hook_event_name": payload.get("hook_event_name"),
        }
        log_path = _probe_log_path()
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass


# --- C3: producer capture at UserPromptExpansion -----------------------------
#
# Spec: docs/plans/2026-08-12-producer-axis-on-the-baton-contract.md chunk C3;
# D1 (host inside this existing registration, no third one), D3 (capture only
# on a CONFIRMED typed slash-command turn -- the value otherwise persists
# until the next one, per the seam's own empirical firing pattern), D6 (write
# the namespaced `producer.typed_command` record via the engine entrypoint,
# never hand-write `session-shape.json`).


def _log_producer_capture_failure(
    session_id: str, typed_command: str | None, reason: str
) -> None:
    try:
        record = {
            "ts": time.time(),
            "event": "producer_capture_failed",
            "session_id": session_id,
            "typed_command": typed_command,
            "reason": reason,
        }
        log_path = _probe_log_path()
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception:
        pass


def _capture_producer(
    payload: dict, command_name: str, session_id: str, cwd: str | None
) -> None:
    if payload.get("expansion_type") != "slash_command":
        return

    typed_command = command_name if command_name else "unresolved"

    if not session_id:
        # Review: code-reviewer -- unlike the not-a-slash-command gate above
        # (an intentional D3 no-op), this is a genuine failure: a CONFIRMED
        # slash-command turn with nothing to key the write against. Must log,
        # not bare-return, or it collapses into the same silent skip AC-7
        # forbids on every other branch in this function.
        _log_producer_capture_failure(session_id or "", typed_command, "missing_session_id")
        return

    root = _resolve_claude_klabauter_root()
    if not root:
        _log_producer_capture_failure(session_id, typed_command, "engine_unresolvable")
        return

    from _engine_root import place_engine_root_on_path as _place_engine_root_on_path
    _place_engine_root_on_path(root)

    try:
        from coordinator_core.session import shape as _shape
    except Exception:
        _log_producer_capture_failure(session_id, typed_command, "engine_unimportable")
        return

    try:
        ok = _shape.producer_set(session_id, typed_command=typed_command, cwd=cwd)
    except Exception as exc:
        _log_producer_capture_failure(
            session_id, typed_command, f"producer_set_raised:{type(exc).__name__}"
        )
        return

    if not ok:
        _log_producer_capture_failure(session_id, typed_command, "lock_failed")


def _fire_apply(script_path: Path, artifact_path: str, session_id: str) -> None:
    if not session_id:
        return
    try:
        _run_pickup_assemble(
            script_path,
            ["apply", artifact_path, "--session-id", session_id],
            session_id,
            _APPLY_TIMEOUT_SECONDS,
        )
    except _TransportFailure:
        pass


def compute_context(stdin_text: str) -> str | None:
    try:
        payload = json.loads(stdin_text) if stdin_text else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    _log_probe_event(payload)

    inv = read_invocation(payload)
    if inv is None:
        return None

    try:
        _capture_producer(payload, inv.command_name, inv.session_id, inv.cwd or None)
    except Exception as exc:
        _log_producer_capture_failure(
            inv.session_id,
            inv.command_name if inv.command_name else "unresolved",
            f"capture_raised:{type(exc).__name__}",
        )

    is_pickup = inv.command_name in _PICKUP_COMMAND_NAMES
    is_baton_grab = inv.command_name in _BATON_GRAB_COMMAND_NAMES
    if not (is_pickup or is_baton_grab):
        return None

    command_args = inv.command_args
    if not command_args:
        return None

    path_string, prose = split_prose_tail(command_args)
    if is_baton_grab:
        path_string = extract_baton_paths(path_string)
    if not path_string:
        return None

    settings_home = resolve_settings_home()
    script_path = resolve_pickup_assemble_bin(settings_home)
    if script_path is None:
        return None

    try:
        result = _run_pickup_assemble(
            script_path, ["brief", path_string], inv.session_id, _BRIEF_TIMEOUT_SECONDS
        )
    except _TransportFailure:
        return None

    subagent = inv.agent_id is not None
    decisions = decode_decision_payload(result.stdout)

    baton_grab_summary = None
    if is_baton_grab and _stdout_is_well_formed(result.stdout):
        spool_open_count = len([tok for tok in path_string.split(" AND ") if tok])
        baton_grab_summary = _baton_grab_summary(decisions, spool_open_count, subagent)

    if not decisions:
        if baton_grab_summary is not None:
            return baton_grab_summary[:_CONTEXT_BUDGET_CHARS]
        return None

    # DEC-3: apply keys UNIFORMLY off each decision's own resolved
    # `artifact.path`, never the raw `command_args`/`path_string` -- for
    # N==1 and N>1 alike. A missing/empty path (an error-object baton in a
    # mixed N>1 array) skips apply for THAT baton without raising; the
    # render below degrades that baton's segment naturally rather than
    # crashing on a raw subscript. Never fired at all from a subagent's own
    # tool call -- see this function's subagent-guard docstring paragraph.
    if not subagent:
        for decision in decisions:
            if not should_apply(decision):
                continue
            artifact = decision.get("artifact")
            apply_path = (artifact or {}).get("path") if isinstance(artifact, dict) else None
            if isinstance(apply_path, str) and apply_path:
                _fire_apply(script_path, apply_path, inv.session_id)

    pointer_paths = [] if subagent else _write_decision_files(decisions, inv.session_id)
    additional_context = render_additional_context(
        decisions, pointer_paths, prose, subagent_guard=subagent
    )
    if baton_grab_summary is not None:
        additional_context = (
            f"{baton_grab_summary}\n\n{additional_context}"
            if additional_context
            else baton_grab_summary
        )
    if not additional_context:
        return None

    return additional_context[:_CONTEXT_BUDGET_CHARS]


def main(stdin_text: str | None = None) -> int:
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
    except Exception:
        return 0

    additional_context = compute_context(raw)
    if additional_context is None:
        return 0

    try:
        print(context_envelope("UserPromptExpansion", additional_context))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
