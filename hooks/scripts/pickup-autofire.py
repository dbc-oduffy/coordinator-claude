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
coordinator/docs/wiki/computed-skills.md (decision-object JSON schema).

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
log, recording `command_source`/`expansion_type` alongside `command_name` and
`session_id`. Whether a `Skill`-tool (programmatic, EM-initiated) invocation
of `/pickup` fires `UserPromptExpansion` at all is NOT something this
sandboxed authoring pass could determine — that requires an actual live
Skill-tool call inside a running Claude Code session, which is outside this
authoring context's reach. Once this hook is registered and `/reload-plugins`
run, a live dogfood pass (typed `/pickup <path>` vs. `Skill(pickup, ...)`)
can `grep` the probe log's `command_source`/`expansion_type` fields for both
invocation shapes and settle it empirically. See this chunk's final report
for the current disposition.

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
    # Defensive fallback -- a hook script copied/deployed WITHOUT its sibling
    # _engine_root.py (e.g. an isolated test harness, or a partial deploy)
    # must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

try:
    from _forwarder_resolve import forwarder_argv as _forwarder_argv  # noqa: E402
    from _forwarder_resolve import resolve_forwarder as _resolve_forwarder  # noqa: E402
except Exception:
    # Defensive fallback -- a deploy missing its sibling _forwarder_resolve.py must
    # degrade to the pre-existing extensionless-only behaviour (which the caller
    # already treats as a fail-open transport failure), never crash on import.
    def _resolve_forwarder(bin_dir, name):  # type: ignore[misc]
        candidate = bin_dir / name
        return candidate if candidate.is_file() else None

    def _forwarder_argv(script_path, tail=()):  # type: ignore[misc]
        return [sys.executable, str(script_path), *tail]

# --- Constants -------------------------------------------------------------

# The set of `command_name` values this hook reacts to. A plain set (not a
# single string) because AC9(a)'s cheap `command_name` matcher is a gate, not
# a security boundary — see the module docstring's clause (a). Extending this
# set (e.g. if `/pickup` ever grows an alias) is a one-line change here.
_PICKUP_COMMAND_NAMES = frozenset({"pickup"})

# Commands that take batons among OTHER arguments. `/pickup`'s entire argument
# string is a path string; `/mise-en-place`'s is not (it also carries tail-mode
# flags and PM-named item identifiers), so its baton paths are extracted by
# family before anything reaches `pickup-assemble` — see
# `extract_baton_paths`. Everything downstream of that extraction is shared:
# handing batons to a run IS a grab, so it briefs, claims, and renders through
# exactly the same path `/pickup` uses. There is deliberately no second claim
# mechanism for the mise surface.
_BATON_GRAB_COMMAND_NAMES = frozenset({"mise-en-place"})

# Path families that carry a claim lifecycle — the only tokens worth briefing
# out of a mixed argument string. Handoffs and cross-repo memos (plus their
# archived counterparts, which resolve through the assembler's own
# archive-fallback) are exactly what `pickup-assemble` classifies; a plan path
# handed to `/mise` for execution is inventory input, not a baton, and must
# NOT be briefed. Matched as a path SEGMENT so absolute, `./`-prefixed, and
# backslash-separated spellings all resolve identically.
_BATON_PATH_FAMILIES = (
    "state/handoffs/",
    "archive/handoffs/",
    "cross-repo/inbox/",
    "cross-repo/archive/",
)


def _normalize_command_name(name: str | None) -> str:
    """Normalize a raw `command_name` payload value to its bare verb.

    Provenance: the live `UserPromptExpansion` payload for the plugin slash
    command delivers `command_name` NAMESPACED as `<plugin>:<command>` (e.g.
    `"coordinator:pickup"`) on the `command_source: "plugin"` path, while
    `projectSettings`/`typed` sources deliver the bare verb (`"pickup"`)
    directly — confirmed from this hook's own probe log during the
    2026-07-24 live dogfood. `_PICKUP_COMMAND_NAMES` is a bare-verb set, so
    matching against the raw payload value silently misses every namespaced
    invocation; this function strips any `<namespace>:` prefix by taking the
    segment after the LAST `:`, so both shapes (and any future plugin
    namespace) normalize to the same bare verb before the membership test.

    Returns `""` for `None`/non-`str` input — that value can never be a
    member of `_PICKUP_COMMAND_NAMES`, so the caller's match fails cleanly
    without a crash.
    """
    if not isinstance(name, str):
        return ""
    return name.rsplit(":", 1)[-1]

# AC9(d) — additionalContext hard cap.
_CONTEXT_BUDGET_CHARS = 10_000

# DEC-1 — prose-tail delimiter. Whitespace-tolerant (NOT a literal single-
# space " -- " string split, which would miss a double-space paste like
# "a.md  --  prose") to mirror the engine repo's own whitespace-bounded `\s+AND\s+`
# token (`split_artifact_args`, `pickup_assemble/__init__.py:3739`).
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

#: `AND` token, whitespace-bounded — mirrors the engine-side artifact-argument
#: splitter, so a multi-baton string tokenizes the same way on both sides of
#: the seam.
_AND_SPLIT_RE = re.compile(r"\s+AND\s+", flags=re.IGNORECASE)


def _is_baton_path(token: str) -> bool:
    """True iff `token` names an artifact family that carries a claim lifecycle.

    Normalization goes through `PureWindowsPath`, which accepts BOTH separators
    on every host, so a Windows-spelled (or mixed-separator) path matches the
    same families as its POSIX spelling regardless of the platform this hook
    runs on — a hardcoded backslash literal would be the same assumption in
    reverse. A leading `-` (any flag, including `--hibernate`) can never match,
    since no family marker contains one.
    """
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


# Subprocess timeouts. `brief` is read-only and fast; `apply` may commit, so
# it gets more headroom. Both are well inside the hooks.json entry's own
# timeout (see hooks.json's registration comment) so a hung subprocess is
# reaped by this module's own timeout before the harness's hook-level one
# fires — giving `main()` a chance to fail open cleanly (AC9c) rather than
# being killed mid-render.
_BRIEF_TIMEOUT_SECONDS = 12
_APPLY_TIMEOUT_SECONDS = 20

# Windows console-subprocess discipline: `python.exe` is a CONSOLE-subsystem
# child. `getattr` resolves to 0 (no-op) on every non-Windows platform.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_PROBE_LOG_NAME = "pickup-autofire-events.jsonl"
# Review: code-reviewer -- env override so callers (tests, or any future
# per-machine isolation need) can point the probe log at a scoped file
# instead of the one fixed OS-tempdir path every process shares.
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
    """Resolve the installed `pickup-assemble` forwarder under `settings_home`.

    Returns the extensionless script or the native `.exe`, whichever the install
    carries, or None when neither is found — the caller treats a None return as a
    transport failure and fails open (AC9c), never a crash.

    Probing the extensionless name alone (what this did) resolved nothing on a
    Windows box carrying the native-forwarder generation, so pickup autofire simply
    stopped firing there, silently.

    Negative-spec: still does NOT resolve `bin/pickup-assemble.cmd` — see
    `_forwarder_resolve`'s negative-spec for why (`CreateProcess` cannot launch one,
    and the extensionless script and native `.exe` between them cover every platform
    the forwarder installer targets).
    """
    return _resolve_forwarder(settings_home / "bin", "pickup-assemble")


def pickup_assemble_argv(script_path: Path, tail: list[str]) -> list[str]:
    """Build the subprocess argv for invoking the resolved forwarder.

    The interpreter prefix is decided by which variant resolved, not assumed: an
    extensionless naked-Python script requires it, a native `.exe` must be launched
    bare. See `_forwarder_resolve.forwarder_argv`.
    """
    return _forwarder_argv(script_path, tail)


# --- Subprocess invocation (fail-open per AC9c) ------------------------------


class _TransportFailure(Exception):
    """Raised internally when a `pickup-assemble` invocation could not be
    completed at all (binary unresolvable, spawn failure, or timeout) — as
    opposed to the target CLI running and returning a non-zero *business*
    exit code, which still yields usable stdout and is not a transport
    failure from this hook's point of view."""


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
    argv = pickup_assemble_argv(script_path, tail)
    try:
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
    """Parse a `pickup-assemble brief`/`apply` stdout blob into a list of
    decision-object dicts (DEC-2), normalizing the N==1/N>1 cross-repo output
    shapes pinned in this module's docstring:
      - a bare JSON object (N==1)  -> `[obj]`
      - a bare JSON array (N>1)    -> its dict elements, in order; any
        non-dict element (e.g. a malformed/error entry that isn't even a
        dict) is DROPPED rather than crashing the caller
      - anything else (unparseable stdout, a bare scalar, a `{"briefs":
        [...]}`-wrapped dict, or any other shape) -> `[]` (fail-open, AC9c)

    A `{"briefs": [...]}`-wrapped dict is itself a bare JSON *object* as far
    as `json.loads` is concerned, so it decodes to a ONE-element list holding
    the wrapper dict verbatim — it is never unwrapped into its `briefs`
    elements. There is no such unwrapping code path anywhere in this module
    (see the module docstring's cross-repo consumer contract, DEC-2).
    """
    try:
        obj = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list):
        return [item for item in obj if isinstance(item, dict)]
    return []


# --- Decision-object predicates (AC9b) ---------------------------------------


def coast_verdict(decision: dict) -> str | None:
    """The `gates.coast.verdict` string, or None when absent/malformed.

    Negative-spec (AC9b): an absent or unrecognized verdict must read as
    HOLD, never as permission — returning None here (rather than defaulting
    to any particular string) makes that the only possible outcome at the
    call site, since `_should_apply` compares for equality against the
    literal string `"clear"`.
    """
    gates = decision.get("gates")
    if not isinstance(gates, dict):
        return None
    coast = gates.get("coast")
    if not isinstance(coast, dict):
        return None
    verdict = coast.get("verdict")
    return verdict if isinstance(verdict, str) else None


def judgment_points_are_empty(decision: dict) -> bool:
    """True iff `judgment_points` is present, a list, and empty."""
    jps = decision.get("judgment_points")
    return isinstance(jps, list) and len(jps) == 0


def should_apply(decision: dict) -> bool:
    """AC4/C3 body: apply ONLY on `coast == clear` AND `judgment_points ==
    []`. Composes `coast_verdict`'s absent-means-hold guarantee with an
    explicit empty-list check — either signal alone gates the mutation.
    """
    return coast_verdict(decision) == "clear" and judgment_points_are_empty(decision)


# --- additionalContext rendering (AC9d) --------------------------------------


def _resolve_repo_root() -> Path | None:
    """Zero-spawn mirror of the engine repo's `apply.py::resolve_repo_root` (default
    `start=None` -> `Path.cwd()`, then `git rev-parse --show-toplevel`).

    Docs/plans/2026-08-07-pickup-hold-path-decision-file-has-no-pr.md — the
    engine resolves the repo root from the SAME cwd this hook's own process
    already has: `_run_pickup_assemble` never overrides the child's `cwd`,
    so the `apply`/`brief` subprocess inherits this hook process's own OS
    cwd (not `payload["cwd"]`, which is only advisory). Reimplemented here
    as a pure-Python upward walk for a `.git` entry (directory for a normal
    clone; worktrees are banned by doctrine, so no file-vs-dir branch is
    needed) rather than shelling out to `git rev-parse` -- this hook's own
    zero-spawn discipline (see `resolve_settings_home`'s sibling resolvers
    in `_engine_root.py`), and `rev-parse --show-toplevel` itself performs
    exactly this upward walk, so the two resolutions land on the same
    answer for any non-worktree checkout.

    Returns None when undeterminable -- callers treat that identically to
    any other decision-file-write failure (AC5): omit the pointer segment,
    never raise.
    """
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
    """Byte-for-byte mirror of the engine repo's
    `coordinator_core/pickup_assemble/apply.py::_sanitize_for_filename`
    (resolve the engine repo's root via `machine-local get repos.claude_klabauter`) --
    collapses BOTH path separators to `__` so a session id or artifact path
    round-trips into one flat filename component. Docs/plans/2026-08-07-
    pickup-hold-path-decision-file-has-no-pr.md, AC1: this hook and
    `apply.py::_session_decision_file_path` must compute the identical
    filename from the identical two inputs, independently."""
    return value.replace("/", "__").replace("\\", "__")


def _session_decision_file_path(repo_root: Path, session_id: str, artifact_path: str) -> Path:
    """Byte-for-byte mirror of the engine repo's
    `apply.py::_session_decision_file_path`/`_session_decision_file_dir` --
    "the ONE deterministic location both the auto-fire hook and `apply`
    independently compute from the same two inputs (session id, artifact
    path)". `.git` is used directly (never a worktree `.git`-file
    redirection lookup) because worktrees are banned by doctrine -- see
    `_resolve_repo_root`'s docstring."""
    name = f"{_sanitize_for_filename(session_id)}__{_sanitize_for_filename(artifact_path)}.json"
    return repo_root / ".git" / "coordinator-sessions" / "decisions" / name


def _write_decision_files(decisions: list[dict], session_id: str) -> list[Path]:
    """Best-effort: write EACH decoded decision to its own engine-computed
    path (`_session_decision_file_path`), keyed off that baton's OWN
    resolved `artifact.path` -- one file per baton, never a shared file
    holding a list (AC2). This is the hold-path discharge location the engine
    repo's `apply.py::_read_session_dispositions` actually reads
    (docs/plans/2026-08-07-pickup-hold-path-decision-file-has-no-pr.md);
    the previous `_write_pointer_file` wrote a tempfile no engine code path
    ever consumed.

    A decision with a missing/empty `artifact.path` is skipped without
    raising (AC3), mirroring DEC-3's own skip-without-raising behaviour for
    an error-object baton carrying no path -- sibling batons in the same
    grab still get their files.

    Total-function, same contract `_write_pointer_file` held (AC5): the
    whole operation is wrapped in ONE try/except, so any `OSError`
    (unresolvable repo root, unwritable `.git`, missing dir, permission)
    degrades the WHOLE call to `[]` -- the render then omits the pointer
    segment entirely, never a partial pointer to a file that could not be
    fully written. Never raises.
    """
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
                continue  # AC3 -- skip a pathless baton without raising
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
    """The `judgment_points` slice retained in the droppable evidence tail
    (C4b): each judgment_point's `dispositions[]` has its guidance-bearing
    entries stripped (they were promoted to `_your_call_text` above), leaving
    non-guidance dispositions and every other judgment_point field (`id`,
    `question`, `recommendation`, ...) untouched. `gates` alone (no
    judgment_point guidance) may remain in evidence per C4b's chunk body --
    this only trims what `_your_call_text` already promoted, never the whole
    key.
    """
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
    """True iff the Evidence tail would carry a fact beyond what
    `verdict_text` already states (`coast=<verdict>, judgment_points=<count>`).

    Guards the C6 (docs/plans/2026-08-02-guard-message-character-cap.md)
    suppression below: a non-empty `judgment_points` is always informative
    (its content, not just its count, is the point); an empty one falls
    through to `gates` -- informative only when `gates` carries a key besides
    `coast`, or `gates.coast` carries a key besides `verdict` (both already
    fully named in `verdict_text`). The common "clear, nothing to decide"
    happy path has neither, so its Evidence tail would be a byte-for-byte
    restatement of the Verdict line under a JSON label -- Evidence exists to
    preserve raw decision data for a genuinely complex decision, not to
    double-print a trivial one.
    """
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
    """
    if not decisions:
        return ""

    multi = len(decisions) > 1
    prose_text = f"EM note: {prose}" if prose else None

    per_baton = [_decision_segments(d, i, multi) for i, d in enumerate(decisions)]

    protected: list[tuple[str, str | None]] = []
    if prose_text:
        protected.append(("prose", prose_text))
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

    # Drop from the tail (evidence, then pointer) — never drop a protected
    # segment (prose / narration / verdict / next_move) as a whole.
    while len(rendered) > _CONTEXT_BUDGET_CHARS and len(kept) > len(protected):
        kept.pop()
        rendered = _join(kept)

    if len(rendered) > _CONTEXT_BUDGET_CHARS:
        kept = list(protected)
        if not narration_slots:
            # Review: code-reviewer -- no narration text anywhere to
            # sacrifice, so the usual per-character narration truncation
            # below has nothing to work with. Rather than falling straight
            # to a raw character slice of the whole protected join (which
            # can and will land mid-string inside some later baton's
            # next_move, violating DEC-4's "next_move is never dropped"
            # invariant for realistic multi-baton payloads), drop WHOLE
            # later-baton (verdict, next_move, your_call) triples from the
            # tail first, one baton at a time, keeping earlier batons
            # intact. Only once a single (earliest) baton's own protected
            # segment alone still overflows the budget do we fall back to a
            # raw slice -- at that point no whole-segment drop can help.
            num_batons = len(per_baton)
            for keep_count in range(num_batons, 0, -1):
                trial = protected[: baton_offset + keep_count * 4]
                trial_rendered = _join(trial)
                if len(trial_rendered) <= _CONTEXT_BUDGET_CHARS or keep_count == 1:
                    return trial_rendered[:_CONTEXT_BUDGET_CHARS]
            return _join(kept)[:_CONTEXT_BUDGET_CHARS]

        texts = {i: (kept[i][1] or "") for i in narration_slots}
        # Review: code-reviewer -- `rest` depends only on `kept` and
        # `narration_slots`, neither of which the loop mutates (only
        # `texts` does); hoisted out of the loop so it's computed once
        # instead of once per character-truncation iteration.
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


# --- Skill-tool-firing measurement instrumentation ---------------------------


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
    `command_name`/`command_source`/`expansion_type`/`session_id` to a
    tempfile-backed log, regardless of whether `command_name` matched a
    pickup verb. This is the durable residue a later live dogfood pass reads
    to settle whether a `Skill`-tool (programmatic) invocation of `/pickup`
    fires `UserPromptExpansion` at all — see the module docstring's own
    "Skill-tool-firing measurement" section for why this authoring pass could
    not settle that question directly. Never raises; a logging failure is
    invisible to the rest of the hook.

    TODO(dogfood-decision): this log has no rotation or size bound. It
    exists solely to answer the Skill-tool-firing question above; once that
    question is settled empirically (see the module docstring's disposition
    note), remove this instrumentation entirely rather than adding
    rotation — it was never meant to be permanent.
    """
    try:
        record = {
            "ts": time.time(),
            "command_name": payload.get("command_name"),
            "command_source": payload.get("command_source"),
            "expansion_type": payload.get("expansion_type"),
            "session_id": payload.get("session_id"),
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
    """Best-effort append to the SAME probe log `_log_probe_event` already
    writes (`_probe_log_path`) -- this file's one existing diagnostic
    channel, reused rather than a second one invented, so a failed capture is
    discoverable by grep instead of degrading into a legitimate-looking
    absence.

    Never raises (mirrors `_log_probe_event`'s own contract) -- a hot-path
    hook that crashed while trying to report a failure would be strictly
    worse than the failure itself, on a machine running a dozen-plus
    concurrent sessions through this same code path.

    This is NOT the `unresolved` in-band signal `producer_set`'s own contract
    reserves for "the field was expected and did not resolve" (see
    `_capture_producer`, which writes that value itself when applicable) --
    a lock failure means NOTHING was written to `session-shape.json` at all,
    so there is no on-disk record to mark as unresolved; this out-of-band log
    line is the only surface that failure gets.
    """
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
        # Broader than OSError on purpose: the docstring above promises this
        # never raises, and `main`'s last-resort guard now calls this function to
        # report a defect that reached it. A narrower catch would let a path- or
        # serialization-level failure escape the reporter itself and surface in
        # the harness — the one outcome worse than the failure being reported.
        pass


def _capture_producer(
    payload: dict, command_name: str, session_id: str, cwd: str | None
) -> None:
    """Capture the typed command for THIS turn into `session-shape.json`'s
    namespaced `producer` record, via the engine's `producer_set` entrypoint
    (never a direct write -- D2/D6).

    Fires ONLY on a turn `expansion_type` confirms is a typed slash command
    (D3's empirical basis: every observed firing was `command_source:
    "plugin"` / `expansion_type: "slash_command"`, and the corrected
    staleness bound holds the value stable across every OTHER turn until the
    next one) -- checking `expansion_type` directly rather than assuming
    every firing of this hook is itself a slash-command turn, per the plan's
    explicit instruction not to assume that.

    Three outcomes, per D6's contract on `producer_set`'s `typed_command`
    parameter:
      - a confirmed slash command whose `command_name` normalizes to a
        non-empty string -> that normalized name (the common case).
      - a confirmed slash command whose `command_name` did not resolve to a
        usable string -> `"unresolved"` (D6's in-band "the field was
        expected and did not resolve" signal -- NOT silently skipped, which
        would read identically to "nothing typed", a collapse AC-3 forbids).
      - anything not confirmed a slash command -> no call at all, leaving
        the prior value in place per D3's persistence bound.

    A `False` return from `producer_set` (lock acquisition failed -- nothing
    was written) is surfaced via `_log_producer_capture_failure`, never
    swallowed and never inferred as success (AC-7). Never raises -- every
    step here degrades to a silent no-op or a logged failure, matching this
    file's fail-open convention for every other subsystem it drives.
    """
    if payload.get("expansion_type") != "slash_command":
        return  # not a confirmed slash-command turn -- leave prior value (D3)

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
        # Fail OPEN (never crash the hot path) but not SILENT: an unresolvable
        # engine means every baton minted this session carries no producer, and
        # an unlogged skip here is indistinguishable from "nothing was typed" --
        # the legitimate-looking absence AC-7 exists to forbid.
        _log_producer_capture_failure(session_id, typed_command, "engine_unresolvable")
        return

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        from coordinator_core.session import shape as _shape
    except Exception:
        # Same reasoning as the unresolvable-root branch above: open, not silent.
        _log_producer_capture_failure(session_id, typed_command, "engine_unimportable")
        return

    try:
        ok = _shape.producer_set(session_id, typed_command=typed_command, cwd=cwd)
    except Exception as exc:
        # producer_set raises only on an out-of-contract typed_command value
        # (never str/None, or an empty string) -- this call always passes a
        # non-empty str, so this branch should be unreachable in practice.
        # Guarded anyway: a hot-path hook must never let a defect here become
        # an unhandled exception (AC-7's "loud" is a log line, not a raise).
        _log_producer_capture_failure(
            session_id, typed_command, f"producer_set_raised:{type(exc).__name__}"
        )
        return

    if not ok:
        _log_producer_capture_failure(session_id, typed_command, "lock_failed")


# --- Mutating half (AC9a) ----------------------------------------------------


def _fire_apply(script_path: Path, artifact_path: str, session_id: str) -> None:
    """Best-effort apply — never raises, never surfaces its own exit code to
    the rest of this hook (AC9c/AC9g: exit 0 reports success, 1/2 mean
    apply's own re-resolved gates changed their mind between brief-time and
    apply-time and it halted/denied without mutating further, 3/4 mean
    transport-failure/partial-mutation and both fail open identically —
    every one of those outcomes is invisible to the EM through this hook;
    the rendered `additionalContext` already reflects the brief-time
    decision, and `/pickup` is never blocked on apply's result).

    Never overrides a denied claim: this function is only ever called by
    `main()` when `should_apply()` returned True, which requires `coast ==
    "clear"` — a state `compute_coast` (engine-side) never reports when the
    claim was denied.
    """
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


# --- Entry point --------------------------------------------------------------


def main(stdin_text: str | None = None) -> int:
    try:
        raw = stdin_text if stdin_text is not None else sys.stdin.read()
    except Exception:
        return 0  # fail-open -- stdin unreadable

    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    _log_probe_event(payload)

    command_name = _normalize_command_name(payload.get("command_name"))

    session_id = payload.get("session_id")
    session_id = session_id if isinstance(session_id, str) else ""

    cwd_value = payload.get("cwd")
    cwd_value = cwd_value if isinstance(cwd_value, str) else None

    # C3: capture the typed command for EVERY confirmed slash-command turn,
    # not just the pickup/baton-grab verbs the rest of this hook reacts to --
    # never let this crash the hot-path hook (AC-7's "loud" is the log line
    # inside `_capture_producer` itself, not an unhandled exception here).
    try:
        _capture_producer(payload, command_name, session_id, cwd_value)
    except Exception as exc:
        # `_capture_producer` documents itself as never-raising, so this guard is
        # unreachable by design and exists only so a defect inside it cannot take
        # down a hook that fires on every prompt for every session on this
        # machine. It still must not be the one silent hole in the capture path:
        # a bare `pass` here would make exactly the unlogged skip AC-7 forbids,
        # and would hide the bug that reached it.
        # Review: code-reviewer -- normalize the same way `_capture_producer`'s
        # own internal calls do (command_name or "unresolved"), so this
        # outer-guard record's `typed_command` field is directly comparable
        # to the inner ones when grepping the probe log.
        _log_producer_capture_failure(
            session_id,
            command_name if command_name else "unresolved",
            f"capture_raised:{type(exc).__name__}",
        )

    is_pickup = command_name in _PICKUP_COMMAND_NAMES
    is_baton_grab = command_name in _BATON_GRAB_COMMAND_NAMES
    if not (is_pickup or is_baton_grab):
        return 0  # not a baton-taking verb -- silent pass

    command_args = payload.get("command_args")
    command_args = command_args.strip() if isinstance(command_args, str) else ""
    if not command_args:
        return 0  # nothing to compute a brief against

    # DEC-1: strip an optional ` -- <prose>` tail BEFORE the path string
    # reaches `pickup-assemble brief` -- the prose never touches path
    # resolution (AC4).
    path_string, prose = split_prose_tail(command_args)
    if is_baton_grab:
        # A mixed argument string: keep only the claim-lifecycle artifacts,
        # discard flags/identifiers/plan paths. No baton named means this is
        # an ordinary backlog run, not a grab -- pass silently.
        path_string = extract_baton_paths(path_string)
    if not path_string:
        return 0  # prose-only invocation -- nothing to compute a brief against

    settings_home = resolve_settings_home()
    script_path = resolve_pickup_assemble_bin(settings_home)
    if script_path is None:
        return 0  # transport failure (AC9c) -- CLI unresolvable, fail open

    try:
        result = _run_pickup_assemble(
            script_path, ["brief", path_string], session_id, _BRIEF_TIMEOUT_SECONDS
        )
    except _TransportFailure:
        return 0  # AC9c

    decisions = decode_decision_payload(result.stdout)
    if not decisions:
        return 0  # AC9c -- unparseable/empty output is a transport failure too

    # DEC-3: apply keys UNIFORMLY off each decision's own resolved
    # `artifact.path`, never the raw `command_args`/`path_string` -- for
    # N==1 and N>1 alike. A missing/empty path (an error-object baton in a
    # mixed N>1 array) skips apply for THAT baton without raising; the
    # render below degrades that baton's segment naturally rather than
    # crashing on a raw subscript.
    for decision in decisions:
        if not should_apply(decision):
            continue
        artifact = decision.get("artifact")
        apply_path = (artifact or {}).get("path") if isinstance(artifact, dict) else None
        if isinstance(apply_path, str) and apply_path:
            _fire_apply(script_path, apply_path, session_id)

    pointer_paths = _write_decision_files(decisions, session_id)
    additional_context = render_additional_context(decisions, pointer_paths, prose)
    if not additional_context:
        return 0

    # Review: code-reviewer -- wrap the final stdout write so a
    # BrokenPipeError (or any other OSError) at exactly this point still
    # honors the module docstring's absolute "main() never raises" claim
    # (AC9c).
    try:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptExpansion",
                        "additionalContext": additional_context,
                    }
                }
            )
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
