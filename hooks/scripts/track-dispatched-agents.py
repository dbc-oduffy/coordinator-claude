#!/usr/bin/env python3
"""SubagentStart + PostToolUse(Agent) naked-Python bookkeeping dispatcher.

C3 (docs/plans/2026-08-10-adopt-harness-native-hook-capabilities.md) split
the write across two events. `SubagentStart` carries `agent_id`/`agent_type`
as first-class fields and fires before the agent-dies-early failure mode
that motivated this move; it makes the CREATE call, identity-only (see
`_build_subagent_start_params`). `PostToolUse(Agent)` -- the original
registration this module replaced the former bash cascade for -- is reduced
to the ENRICH call, supplying the real resolved `dispatched_model`. Both
calls go through the same engine op (`hooks.track_dispatched_agents`).

**The create call sends the REAL `agent_type`, not a placeholder.** It once
sent `"unknown"` so the enrich call would land on the collision resolver's
enrich-in-place branch rather than its idempotent-dedup branch, preserving
the model. That traded away the only identity signal a WORKFLOW-spawned
agent ever gets: `PostToolUse(Agent)` does not fire for a `Workflow`
`agent()` spawn at all, so its row kept the placeholder permanently, and the
two guards keyed on column 3 failed in opposite directions off that one
string -- the plan-body deny could not key (fail-open) and the sanctioned
commit agent was refused as an unrostered type (fail-closed).

Cost of the current shape, measured on live rows rather than predicted: on
the RAW-AGENT-ID path both calls key the same row, so the enrich call now
matches on type, takes the resolver's dedup arm, and its model is dropped --
a built-in-type dispatch that read `<id> claude-sonnet-5 Explore` before this
change reads `<id> unknown Explore` after. Rows keyed by a NAMED agent id
(`<name>@session-<sid6>`) are unaffected and still carry a real model. It
closes when the collision resolver learns to adopt a real model onto a row
whose type already matches; the engine plane owns that half and has it
planned. No consumer branches on the string: the runtime-tripwire watchers
fall through to their opus-default threshold and session-LoE undercounts
opus dispatches. Estimate quality, not correctness.

The resolver's AMBIGUOUS arm (two real, differing types on one row) is the
failure this change could plausibly have opened, since a real type now meets
the enrich call's `tool_input.subagent_type` instead of a placeholder. Not
reproduced: zero AMBIGUOUS rows across a post-change sweep spanning
`coordinator:*` types and a built-in type. Measured, not proven -- if a
spelling mismatch is ever found, normalize both sides at the comparison
rather than reverting to the placeholder. See
`_SUBAGENT_START_PLACEHOLDER_TYPE`.

Replaces the former bash PostToolUse(Agent)
registration (agentId/model/subagent_type bookkeeping writes) with ONE
`python3` hook entry -- zero Git-Bash cold-start per Agent-tool return on
Windows (each bash.exe spawn costs 200-500ms; this is the whole point).

The doctrine plane owns only this thin PLUMBING shim (DR-047 transport-seam carve-out): parse
the raw PostToolUse payload, extract the same flat scalars the legacy bash
cascade computed, resolve the claude-klabauter engine, hand it the mapped params, relay
its stdout. Claude-klabauter owns the write LOGIC (coordinator_core.hooks.
track_dispatched_agents, registered under "hooks.track_dispatched_agents") --
the dedup/collision-rewrite/append to dispatched-agents.txt and the atomic
em-session-id.txt back-pointer. The engine is imported and run IN-PROCESS via
coordinator_core.ipc.dispatch_from_hook (DR-175 -- the named hook-dispatch
seam, above the dispatch_message telemetry wrapper) -- no bash, no
`python3 -m` subprocess re-spawn -- so a whole Agent-tool return pays exactly
one Python interpreter start.

Contract (mirrors the retired bash hook it replaces):
  stdin   -- PostToolUse JSON (tool_name, tool_input, tool_response,
             session_id, cwd, ...)
  stdout  -- NOTHING (this op returns no_advisory() unconditionally; its
             product is the on-disk write side-effect, not stdout)
  exit 0  -- always (advisory bookkeeping; never blocks the Agent tool call)
  As of the posttooluse-non-fire diagnostic, `main()` also appends one line
  to a scratch canary log before any other processing; see
  `_write_posttooluse_agent_canary`.

stdin -> params mapping (op scope "common_dir" -- REQUIRES _origin_worktree;
see coordinator_core/ipc.py _OP_KEY_SCOPE["hooks.track_dispatched_agents"] =
"common_dir", and W2-stub-contract.md § 3's bookkeeping-ops caveat).
Unlike postuse_advisory_dispatch (op scope "none", flat stdin-key ==
params-key identity mapping), this op's handler does NOT do its own field
extraction from tool_response/tool_input -- its docstring's "R-1" note says
dispatched_agent_id / dispatched_model / subagent_type arrive as FLAT SCALARS
"pre-resolved by manifest" (the mcp_tool-era three-pass / four-source
cascades). This stub is not going through mcp_tool, so it must itself run
those same cascades over the raw JSON payload before calling the op --
mirroring the retired bash hook's extraction logic exactly (see
_extract_dispatch_fields below), not just relaying stdin keys 1:1.

On PostToolUse(Agent) (enrich call):
    session_id                <- stdin["session_id"]                          (top level)
    dispatched_agent_id       <- stdin["tool_response"]["agentId"]            (pass a, camelCase)
    dispatched_agent_id_snake <- stdin["tool_response"]["agent_id"]           (pass a, snake_case)
    dispatched_model           <- tool_response.resolvedModel
                                   -> tool_response.model
                                   -> tool_input.model
                                   -> "" (handler itself defaults "" to "unknown")
    subagent_type               <- tool_input.subagent_type -> "" (handler defaults "unknown")

On SubagentStart (create call, see `_build_subagent_start_params`):
    session_id                <- stdin["session_id"]                          (top level)
    dispatched_agent_id       <- stdin["agent_id"]                            (top level)
    dispatched_model           <- _SUBAGENT_START_PLACEHOLDER_TYPE ("unknown", never resolved)
    subagent_type               <- stdin["agent_type"] -> _SUBAGENT_START_PLACEHOLDER_TYPE if
                                    absent/non-string (see module docstring: this now lands the
                                    enrich call on the idempotent-dedup branch instead of the
                                    enrich branch, stranding model -- see Finding 3 in the review
                                    trail for the accepted regression this causes)

Handler-side validation NOT replicated here (belongs to claude-klabauter, not this
stub): agent-id format guard (bare-hex >=12 / teammate canonical id), the
session_id/agent_id required-field early-outs, and the model/subagent_type
"" -> "unknown" fallback -- all already implemented in
coordinator_core/hooks/track_dispatched_agents.py's handler. This stub only
extracts and forwards; it does not duplicate that logic.

_origin_worktree (REQUIRED -- "common_dir" scope): set to stdin["cwd"], the
same field preuse-write-dispatch.py already extracts for its own (non-scoped)
purposes. The op handler resolves this into the shared .git common directory
via coordinator_core.lifecycle.git_common_dir (a `git rev-parse
--path-format=absolute --git-common-dir` subprocess call with cwd=repo_root)
-- claude-klabauter-owned, not this stub's concern; mirrors the same "not the stub's
subprocess" caveat postuse-advisory-dispatch.py's reference contract already
names for the runtime-tripwire's git call. If cwd is absent, dispatch_message
returns an INVALID_PARAMS error response (not a raised exception) -- result is
None, `if result:` is already false, this degrades to the SAME silent no-op
fail-open as every other seam (see W2-stub-contract.md § 3's caveat: this is a
functional regression vs a resolvable cwd, but a safe one -- absent cwd never
crashes or writes partial state).

Event branch: `main()` dispatches on `hook_event_name`. On `SubagentStart`
it runs the create path unconditionally (there is no tool-name gate on this
event -- every fire carries a dispatched agent's identity). On `PostToolUse`
it preserves the legacy tool-name gate: the retired bash hook exited 0
immediately unless tool_name == "Agent" (matcher scoping done in-script, not
via hooks.json matcher alone, historically); this stub keeps that same
early-out -- running the extraction cascade and a full IPC dispatch on every
non-Agent PostToolUse event would be pure waste (the op has no tool_name
gate of its own; the docstring's "R-1" contract assumes the caller already
scoped to Agent-tool returns). Any other hook_event_name value is unreached
in registered use (this script is only ever invoked as SubagentStart or
PostToolUse) and falls through to fail-open.

Graceful degradation -- REQUIRED: any failure to resolve/import/run the
Claude-klabauter engine, or to parse stdin, falls through to fail-open (exit 0, no
stdout). A missing sibling engine must NEVER brick an Agent-tool return --
identical philosophy to preuse-write-dispatch.py._resolve_claude_klabauter_root (kept
in lockstep deliberately; see W2-stub-contract.md).

NOTE (historical): during the bash->Python cutover, the retired bash hook and
this dispatcher briefly co-registered; both writing the same dedup/append-tab-
format file was harmless (idempotent dedup on matching agent_id +
subagent_type), so there was no window with bookkeeping down. The bash hook
is now fully retired; this dispatcher is the only writer.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover -- defensive: PyYAML is a hook-venv
    # dependency, not guaranteed present on whatever interpreter actually
    # runs this hook; an absent yaml must degrade _resolve_contract_blocks
    # to [] (fail-open), never crash before main() is entered. See
    # handoff-segment-inject.py's identical guard.
    yaml = None  # type: ignore[assignment]


def _read_stdin(timeout: float = 2.0) -> str:
    """Bounded stdin read (Windows hang guard) -- copied from
    runtime-tripwire-stop-watcher.py._read_stdin (~186-201).

    A bare sys.stdin.read() blocks forever if the harness never closes
    stdin's write end (observed Windows failure mode), backstopped with a 2s
    threaded-join timeout, returning "" (the same fail-open value a
    JSON-decode failure already produces) instead of hanging the hook chain.
    """
    box = {"data": ""}

    def _read() -> None:
        try:
            box["data"] = sys.stdin.read()
        except Exception:
            box["data"] = ""

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    return box["data"]


_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    # Defensive fallback -- a hook script copied/deployed WITHOUT its
    # sibling _engine_root.py (e.g. an isolated test harness, or a
    # partial deploy) must still fail-open rather than crash on import.
    def _resolve_claude_klabauter_root() -> str | None:
        return None

try:
    from _git_root_walk import git_root_walk as _git_root_walk  # noqa: E402
except Exception:
    # Same defensive-fallback shape as the _engine_root import above -- a
    # deploy missing its sibling _git_root_walk.py must still fail-open.
    def _git_root_walk() -> str | None:
        return None

try:
    from _plan_path_bridge import read_plan_path as _read_plan_path  # noqa: E402
except Exception:
    # Same defensive-fallback shape as the two imports above -- a deploy
    # missing its sibling _plan_path_bridge.py must still fail-open, which
    # here means the plan-derivable leg simply does not fire.
    def _read_plan_path(session_id, subagent_type, cwd) -> str | None:
        return None


# Create-call placeholder: sent as dispatched_model on the SubagentStart
# call, which has no model to report, and as the subagent_type FALLBACK when
# the payload carries no usable agent_type. Matches PLACEHOLDER_TYPE in the
# engine's collision resolver, so a fallback row stays enrichable. A real
# agent_type is sent verbatim -- it is the only identity a workflow-spawned
# agent's row will ever carry; see the module docstring.
_SUBAGENT_START_PLACEHOLDER_TYPE = "unknown"

# Session-id format guard for `_read_backpointer_subagent_type` -- mirrors
# the engine's own `_SESSION_ID_FORMAT_RE` (subagent_sandbox/engine.py)
# verbatim. `em_sid` comes from a first-party file on disk today, but this
# leg builds a filesystem path from it in a fail-open hook, so it is
# validated as a plain token before use rather than trusted on the
# "we wrote it" argument -- a value like `..\..\x` must never walk the
# dispatch-file lookup outside `coordinator-sessions/`.
_SESSION_ID_FORMAT_RE = re.compile(r"^[a-zA-Z0-9_-]{3,}$")


def _extract_dispatch_fields(payload: dict) -> dict[str, str]:
    """Run the same agent-id / four-source model cascade as the bash hook.

    Mirrors the retired bash hook's steps (a)/(c) exactly, operating on the
    already-parsed JSON dict instead of raw-text slicing. Returns "" for any
    field that cannot be resolved -- the op handler's own field()/fallback logic
    treats "" as absent, matching mcp_tool's own convention.
    """
    tool_response = payload.get("tool_response")
    if not isinstance(tool_response, dict):
        tool_response = {}
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    # (a) primary: camelCase agentId (unnamed/background agents).
    dispatched_agent_id = tool_response.get("agentId") or ""
    # (a) fallback: snake_case agent_id (named Agent-Teams teammates).
    dispatched_agent_id_snake = tool_response.get("agent_id") or ""

    # (c) model: resolvedModel -> model (both tool_response) -> tool_input.model -> "".
    dispatched_model = (
        tool_response.get("resolvedModel")
        or tool_response.get("model")
        or tool_input.get("model")
        or ""
    )

    # subagent_type: tool_input only; "" if absent (handler defaults to "unknown").
    subagent_type = tool_input.get("subagent_type") or ""

    return {
        "dispatched_agent_id": dispatched_agent_id if isinstance(dispatched_agent_id, str) else "",
        "dispatched_agent_id_snake": dispatched_agent_id_snake if isinstance(dispatched_agent_id_snake, str) else "",
        "dispatched_model": dispatched_model if isinstance(dispatched_model, str) else "",
        "subagent_type": subagent_type if isinstance(subagent_type, str) else "",
    }


def _build_subagent_start_params(payload: dict) -> dict[str, str] | None:
    """Build the identity-only create-call params from a SubagentStart payload.

    Returns None when the identity field is absent -- the caller degrades to
    fail-open rather than dispatching a params dict with no agent_id.
    """
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    agent_type = payload.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type:
        agent_type = _SUBAGENT_START_PLACEHOLDER_TYPE
    return {
        "dispatched_agent_id": agent_id,
        "dispatched_agent_id_snake": "",
        "dispatched_model": _SUBAGENT_START_PLACEHOLDER_TYPE,
        "subagent_type": agent_type,
    }


def _resolve_git_root_for_backpointer(cwd: Any) -> str | None:
    """Git root anchored on the payload's `cwd` (in-process, zero-spawn),
    falling back to `_git_root_walk` (anchored on `Path.cwd()`) when `cwd`
    is absent or its own walk fails to find a `.git` entry.

    A per-dispatch hot path -- no subprocess, no `git rev-parse`. Never
    raises: any exception on either rung degrades to `None`.
    """
    if isinstance(cwd, str) and cwd:
        try:
            start = Path(cwd).resolve()
            for candidate in (start, *start.parents):
                if (candidate / ".git").exists():
                    return str(candidate)
        except Exception:
            pass
    try:
        return _git_root_walk()
    except Exception:
        return None


def _read_backpointer_subagent_type(git_root: str, agent_id: str) -> str:
    """Back-pointer chain: agent_id -> em_session_id -> dispatched-agents.txt row.

    Mirrors the engine's own subagent-sandbox back-pointer resolver (its
    secondary OR-resolver leg, same chain, same column layout), with two
    deliberate departures documented at the call site: the raw `agent_id`
    is used as the `.agents/` key verbatim (no canonical-id normalization --
    that normalizer's named-teammate regex does not match this shim's live
    `<name>@session-<sid6>` id form, and the `.agents/` directory is keyed
    by the raw payload `agent_id` on disk), and no expected-session scoping
    is applied (the engine's own resolver passes none here either).

    Chain:
      1. `<git_root>/.git/coordinator-sessions/.agents/<agent_id>/
         em-session-id.txt` -> first line, stripped -> `em_sid`.
      2. `<git_root>/.git/coordinator-sessions/<em_sid>/dispatched-agents.txt`
         -> TAB-separated rows: `agent_id \\t model \\t subagent_type \\t epoch`.
         `em_sid` is validated against `_SESSION_ID_FORMAT_RE` (mirroring
         the engine's own format guard) BEFORE it is interpolated into this
         path -- a value that is not a plain session-id-shaped token
         (e.g. a traversal string) is a lookup-fail (`""`), same as any
         other broken chain link, never a path built from untrusted input.
      3. Rows with fewer than 3 columns are ignored outright. Among rows
         whose column 0 == `agent_id`, the LAST match wins (recency),
         mirroring the engine's duplicate-row rule -- deliberately NOT the
         engine's own fail-closed-on-ambiguity rule (this leg has its own
         unconditional fallback-to-payload caller, so a duplicate-row
         ambiguity is safe to resolve by recency rather than refuse).
      4. Column index 2 (the FOURTH tab-separated field) is the
         subagent_type; column index 1 (the model) must never be read here
         -- that column-swap already cost one measurement on the engine
         side.

    Any missing/unreadable/malformed link in the chain returns `""`
    (lookup-fail) rather than raising -- the caller's unconditional
    fallback-to-payload-`agent_type` contract depends on this never raising.
    """
    # Review: code-reviewer -- agent_id comes from the same payload trust
    # boundary as em_sid and is interpolated into a filesystem path below.
    # Unlike em_sid, real agent_id values are `name@session-<sid6>` (contains
    # `@`), so _SESSION_ID_FORMAT_RE cannot be reused verbatim; instead reject
    # path-separator/traversal characters that could walk the lookup outside
    # `coordinator-sessions/.agents/`.
    if not agent_id or "/" in agent_id or "\\" in agent_id or ".." in agent_id:
        return ""
    try:
        backptr = (
            Path(git_root)
            / ".git"
            / "coordinator-sessions"
            / ".agents"
            / agent_id
            / "em-session-id.txt"
        )
        content = backptr.read_text(encoding="utf-8")
    except Exception:
        return ""
    lines = content.splitlines()
    em_sid = lines[0].strip() if lines else ""
    if not em_sid or not _SESSION_ID_FORMAT_RE.match(em_sid):
        return ""

    try:
        dispatch_file = (
            Path(git_root) / ".git" / "coordinator-sessions" / em_sid / "dispatched-agents.txt"
        )
        rows = dispatch_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""

    resolved = ""
    for row in rows:
        fields = row.split("\t")
        if len(fields) < 3:
            continue
        if fields[0] == agent_id:
            resolved = fields[2]  # last match wins (recency)
    return resolved


def _resolve_effective_subagent_type(cwd: Any, agent_id: str, payload_agent_type: str) -> str:
    """The EFFECTIVE subagent_type for `_resolve_contract_blocks`, via a
    back-pointer read that unmasks a NAMED dispatch's real type.

    Why this exists: a NAMED dispatch's SubagentStart payload `agent_type`
    is the teammate NAME, not its subagent_type (see
    `state/bug-backlog/2026-08-21-named-dispatch-catering-resolves-contrac-
    07a62a2e53de.yaml`) -- `_resolve_contract_blocks(policy_file,
    subagent_type)` misses on the raw name and the child is catered EMPTY,
    silently. This resolves the back-pointer chain
    (`_read_backpointer_subagent_type`) FIRST and falls back to
    `payload_agent_type` whenever the read yields nothing, including when
    the resolved value is `_SUBAGENT_START_PLACEHOLDER_TYPE` ("unknown") --
    that placeholder is not a resolution, matching the engine's own
    treatment of it.

    Fail-open, unconditionally: an unreadable/absent/malformed backpointer
    chain, a missing `cwd`/git root, or any exception anywhere in this path
    returns `payload_agent_type` verbatim. Never raises.

    Only `_resolve_contract_blocks`'s INPUT changes -- the op params sent to
    `hooks.track_dispatched_agents` and the `agent_type` sent on the
    `hooks.cater_subagent_start` payload stay the raw payload value
    unchanged; see `_dispatch_subagent_start_ops`.

    **Removal condition** (write it down, do not leave it remembered): this
    is knowingly the effective-type-resolution duplication both sides of
    this seam rejected on principle, accepted here as temporary. Delete
    this leg (and its removal-condition test,
    `test_resolve_effective_subagent_type_removal_condition_is_documented`
    in `test_track_dispatched_agents_catering_relay.py`) once the agreed
    `contract_blocks` MAP shape is live in the served engine mirror -- the
    engine plane's own map-accepting commit already accepts both shapes;
    the switch is safe once their engine row publishes. Blocked on bug id
    `2026-08-21-the-engine-row-cannot-publish-data-root-b0706ca7fc0d`
    (`state/bug-backlog/`); see also the named-dispatch bug above.
    """
    fallback = payload_agent_type if isinstance(payload_agent_type, str) else ""
    try:
        if not agent_id:
            return fallback
        git_root = _resolve_git_root_for_backpointer(cwd)
        if not git_root:
            return fallback
        resolved = _read_backpointer_subagent_type(git_root, agent_id)
        if resolved and resolved != _SUBAGENT_START_PLACEHOLDER_TYPE:
            return resolved
        return fallback
    except Exception:
        return fallback


def _resolve_contract_blocks(policy_file: Path, child_subagent_type: str) -> list[str]:
    """W0 seam (canonical spec `state/subagent-share/conductor/seam-adjudication.md`
    §2.4.1): resolve subagent_type -> ordered block-name list via the
    contract_blocks: key in subagent-sandbox-policy.yaml.

    Eligibility is DATA, not a hardcoded consumer family: any subagent_type
    with a non-empty list here is eligible for prompt-block injection. Real
    yaml.safe_load, same shape as `_resolve_report_type` (contract_blocks: is
    a dict, not a flat list). Fail-open on any parse error, absent file,
    absent key, an unavailable `yaml` module, or an unmapped/empty-list
    subagent_type: return [] and the caller relays nothing.
    """
    if yaml is None or not child_subagent_type or not policy_file.is_file():
        return []
    try:
        policy = yaml.safe_load(policy_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(policy, dict):
        return []
    contract_blocks_map = policy.get("contract_blocks")
    if not isinstance(contract_blocks_map, dict):
        return []
    block_names = contract_blocks_map.get(child_subagent_type)
    if not isinstance(block_names, list):
        return []
    return [name for name in block_names if isinstance(name, str)]


def _resolve_report_type(policy_file: Path, child_subagent_type: str) -> str:
    """Resolve subagent_type -> provisioning template type via the
    report_type_map: key in subagent-sandbox-policy.yaml.

    Sibling of `_resolve_contract_blocks` above and read from the same file in
    the same pass: both are doctrine-plane resolutions the engine deliberately
    does not perform for itself, and both ride the one catering payload this
    shim composes. Without it every provisioned sidecar resolves the engine's
    frozen legacy run-report body regardless of identity -- a reviewer persona
    handed `## Run notes` where its contract promises `## Verdict`/`## Findings`
    reads a scaffold that does not match its own contract and scaffolds a path
    of its own instead, which is how a persona's findings end up outside
    `state/subagent-share/`.

    Fail-open on any parse error, absent file, absent key, an unavailable
    `yaml` module, or an unmapped identity: return "" and the caller sends no
    `type` at all, leaving the engine's own default untouched -- never a
    forced type, never a blocked spawn.
    """
    if yaml is None or not child_subagent_type or not policy_file.is_file():
        return ""
    try:
        policy = yaml.safe_load(policy_file.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(policy, dict):
        return ""
    report_type_map = policy.get("report_type_map")
    if not isinstance(report_type_map, dict):
        return ""
    report_type = report_type_map.get(child_subagent_type)
    return report_type if isinstance(report_type, str) else ""


def _write_posttooluse_agent_canary(raw: str) -> None:
    """Diagnostic scaffolding for
    state/bug-backlog/2026-08-10-posttooluse-agent-does-not-fire-for-some-8c1d40be9f2a.yaml.

    Discriminates whether the PostToolUse(Agent) hook PROCESS ever started
    on a given Agent-tool return: a line present in the canary log means
    this process ran at least this far, so a missing dispatched-agents.txt /
    agent-audit.jsonl row on that spawn is a downstream (in-process) failure;
    a line absent means the harness never delivered or killed the chain
    before this point. Both consumer writers are already exonerated by
    replay (fast, always-exit-0) -- this canary is the only thing that can
    tell the two remaining hypotheses apart. Remove once that bug is closed
    and the discriminator is no longer needed.

    Parses `raw` only (the SAME stdin string `main()` already read via its
    single `_read_stdin()` call) -- never reads stdin itself, so it cannot
    starve `main()`'s own read on a machine running many concurrent
    sessions. Wrapped entirely in try/except: an unwritable path, a full
    disk, or a malformed payload degrades to "no canary line", never to a
    broken hook -- this function's whole contract is fail-open.
    """
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    try:
        tool_name = payload.get("tool_name") or ""
        session_id = payload.get("session_id") or ""
        cwd = payload.get("cwd") or None

        tool_response = payload.get("tool_response")
        if not isinstance(tool_response, dict):
            tool_response = {}
        agent_id = tool_response.get("agentId") or tool_response.get("agent_id") or ""

        probe = Path(cwd).resolve() if isinstance(cwd, str) and cwd else Path.cwd()
        git_dir = None
        for candidate in (probe, *probe.parents):
            marker = candidate / ".git"
            if marker.is_dir():
                git_dir = marker
                break
            if marker.is_file():
                raw_pointer = marker.read_text(encoding="utf-8", errors="replace")
                if not raw_pointer.startswith("gitdir:"):
                    return
                pointer = raw_pointer[len("gitdir:"):].strip()
                if not pointer:
                    return
                pointer_path = Path(pointer)
                if not pointer_path.is_absolute():
                    pointer_path = (candidate / pointer_path).resolve()
                git_dir = pointer_path
                break
        if git_dir is None:
            return

        commondir_file = git_dir / "commondir"
        if commondir_file.is_file():
            raw_common = commondir_file.read_text(encoding="utf-8", errors="replace").strip()
            if not raw_common:
                return
            common_path = Path(raw_common)
            if not common_path.is_absolute():
                common_path = (git_dir / common_path).resolve()
            common_dir = common_path
        else:
            common_dir = git_dir

        log_dir = common_dir / "coordinator-sessions" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{stamp}\t{tool_name}\t{session_id}\t{agent_id}\n"
        # Windows append-atomicity for concurrent writers is NOT independently
        # verified here (see finding 1 in the 0d753c61e canary review, and the
        # closure note in the linked bug-backlog entry): a torn/interleaved
        # line under concurrent CRT "a"-mode writes is an accepted false
        # negative for this discriminator -- a present-but-malformed line
        # still proves the process ran this far, which is the only question
        # this canary exists to answer.
        with (log_dir / "posttooluse-agent-canary.log").open(
            "a", encoding="utf-8"
        ) as fh:
            fh.write(line)
    except Exception:
        return


def main() -> int:
    raw = _read_stdin()
    _write_posttooluse_agent_canary(raw)

    try:
        payload: Any = json.loads(raw)
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    event = payload.get("hook_event_name")

    if event == "SubagentStart":
        fields = _build_subagent_start_params(payload)
        if fields is None:
            return 0  # fail-open -- missing identity field, nothing to write
        session_id = payload.get("session_id") or ""
        cwd = payload.get("cwd") or None
        params = {
            "session_id": session_id if isinstance(session_id, str) else "",
            **fields,
        }
        return _dispatch_subagent_start_ops(cwd, params, payload)

    # PostToolUse(Agent) enrich path -- unreached hook_event_name values
    # (this script is only ever registered on SubagentStart and PostToolUse)
    # fall through this branch and hit the tool-name gate below, which
    # returns 0 on anything but an Agent-tool return.

    # Tool-name gate (mirrors bash line 82): only Agent-tool returns carry a
    # dispatched agentId worth bookkeeping. Cheap early-out before any engine
    # resolution / IPC dispatch cost.
    if payload.get("tool_name") != "Agent":
        return 0

    session_id = payload.get("session_id") or ""
    cwd = payload.get("cwd") or None

    fields = _extract_dispatch_fields(payload)

    params = {
        "session_id": session_id if isinstance(session_id, str) else "",
        **fields,
    }

    return _dispatch_bookkeeping_write(cwd, params)


def _dispatch_subagent_start_ops(cwd: Any, params: dict, payload: dict) -> int:
    """SubagentStart-only two-op relay (2026-08-21 catering cutover, C1):
    `hooks.track_dispatched_agents` (bookkeeping, FIRST) then
    `hooks.cater_subagent_start` (catering, SECOND), through one
    `dispatch_ops_from_hook` call.

    Ordering is a read-after-write dependency, not a preference: catering's
    `resolve_effective_types` resolves a named dispatch's type through a
    back-pointer into `dispatched-agents.txt`, the file the bookkeeping leg
    writes on this SAME event. Reversed, named teammates cater
    nondeterministically. Runbook: the SubagentStop review-mark fold
    (9ded965ba, subagent-zero-tool-use-detect.py) -- same call shape, same
    per-op returned-not-raised failure isolation, reused here rather than
    invented fresh.

    `contract_blocks` is resolved shim-side (not engine-side -- see the
    governing plan's anti-scope: `_resolve_contract_blocks` anchors its
    policy file by plugin-root offset, stable only from inside the plugin)
    and merged onto the catering payload; an unenumerated subagent_type
    resolves to `[]`, a normal outcome not a miss. Its lookup KEY is the
    EFFECTIVE subagent_type from `_resolve_effective_subagent_type` (a
    back-pointer read into `dispatched-agents.txt`, falling back to the
    payload `agent_type`) -- not `params["subagent_type"]` directly -- so a
    NAMED dispatch (whose SubagentStart payload carries the teammate NAME,
    not its subagent_type) still resolves a real `contract_blocks` list
    instead of missing silently. This resolution affects `contract_blocks`
    ONLY: the op params sent to `hooks.track_dispatched_agents` and the
    `agent_type` sent on the `hooks.cater_subagent_start` payload stay the
    raw payload values, unchanged. See `_resolve_effective_subagent_type`'s
    own docstring for the removal condition.

    Emission (AC5): `isinstance(r, HookDispatchError)` discriminates each
    positionally aligned result FIRST -- an errored leg contributes nothing,
    never suppresses its sibling. Every remaining non-empty envelope's
    `additionalContext` is concatenated in relay order (`"\n\n"`-joined,
    matching the PreToolUse emitter's own multi-note join); nothing is
    emitted when all are empty. Concatenation over take-the-one-non-empty is
    deliberate: only catering carries a payload today, but a silent drop is
    the exact failure class this cutover keeps reproducing.
    """
    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Same eager-import cost note as _dispatch_bookkeeping_write below --
        # importing coordinator_core.hooks triggers the package __init__
        # (registers every op via register_op side-effects), once per fire.
        from coordinator_core.hooks import track_dispatched_agents as _op  # noqa: F401
        from coordinator_core.ipc import HookDispatchError, dispatch_ops_from_hook
    except Exception:
        return 0  # engine unimportable -> fail-open

    subagent_type = params.get("subagent_type") or ""
    session_id = payload.get("session_id") or ""
    agent_id = payload.get("agent_id") or ""
    agent_type = payload.get("agent_type") or ""

    effective_subagent_type = _resolve_effective_subagent_type(
        cwd, agent_id if isinstance(agent_id, str) else "", subagent_type
    )
    policy_file = Path(__file__).resolve().parents[2] / "subagent-sandbox-policy.yaml"
    contract_blocks = _resolve_contract_blocks(policy_file, effective_subagent_type)
    report_type = _resolve_report_type(policy_file, effective_subagent_type)

    # The engine's sidecar leg resolves its policy through `load_policy(None)`,
    # whose surviving rungs are the SUBAGENT_SANDBOX_POLICY env var and a
    # CLAUDE_PLUGIN_ROOT-relative default. Only this plane knows where the
    # policy file actually is -- `Path(__file__).parents[2]` is `coordinator/`
    # under both the marketplace and dev-source layouts, while the plugin root
    # differs between them -- and an unresolved policy loads EMPTY, which makes
    # every subagent_type ineligible and provisions nothing at all, silently
    # (the miss notice is itself gated on eligibility). `dispatch_ops_from_hook`
    # is a process-level in-process chokepoint, so this assignment is visible to
    # the handler it relays to.
    os.environ["SUBAGENT_SANDBOX_POLICY"] = str(policy_file)

    catering_payload: dict = {
        "session_id": session_id if isinstance(session_id, str) else "",
        "agent_id": agent_id if isinstance(agent_id, str) else "",
        "agent_type": agent_type if isinstance(agent_type, str) else "",
        "cwd": str(cwd) if cwd else "",
        "contract_blocks": contract_blocks,
    }
    if report_type:
        catering_payload["type"] = report_type
    # A plan-derivable lens's `plan_path` was recorded on PreToolUse(Agent), the
    # only event carrying the child's prompt -- see `_plan_path_bridge`. Absent
    # it, the engine's plan-derivable leg cannot fire and the lens's sidecar
    # falls through to the session-keyed home instead of
    # `state/plan-sidecars/<plan-stem>.<lens>.md`.
    plan_path = _read_plan_path(
        session_id if isinstance(session_id, str) else "",
        effective_subagent_type,
        str(cwd) if cwd else None,
    )
    if plan_path:
        catering_payload["plan_path"] = plan_path

    ops: list[tuple[str, dict]] = [
        ("hooks.track_dispatched_agents", params),
        ("hooks.cater_subagent_start", catering_payload),
    ]

    try:
        # Per-op errors are RETURNED (HookDispatchError instances), never
        # raised, under ONE asyncio.run inside dispatch_ops_from_hook -- a
        # failure in either leg can never suppress the other's result.
        results = dispatch_ops_from_hook(
            ops,
            origin_worktree=str(cwd) if cwd else None,
        )
    except Exception:
        return 0  # any engine failure -> fail-open (never brick a hook fire)

    additional_context_parts: list[str] = []
    for r in results:
        if isinstance(r, HookDispatchError):
            continue  # errored leg contributes nothing, never suppresses its sibling
        if not r:
            continue  # no_advisory()/empty envelope -- normal outcome, not an error
        hook_output = r.get("hookSpecificOutput") if isinstance(r, dict) else None
        if not isinstance(hook_output, dict):
            continue
        note = hook_output.get("additionalContext")
        if isinstance(note, str) and note:
            additional_context_parts.append(note)

    if not additional_context_parts:
        return 0  # all empty -- emit nothing (AC5/AC7)

    out = {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": "\n\n".join(additional_context_parts),
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.write("\n")
    return 0


def _dispatch_bookkeeping_write(cwd: Any, params: dict) -> int:
    """Shared IPC seam for both the SubagentStart create call and the
    PostToolUse(Agent) enrich call -- same op, same in-process dispatch, same
    fail-open contract on either side.
    """
    root = _resolve_claude_klabauter_root()
    if not root:
        return 0  # fail-open -- engine unresolvable on this machine

    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        # Importing coordinator_core.hooks.track_dispatched_agents triggers the
        # coordinator_core.hooks package __init__ (registers all 7 advisory ops +
        # 4 bookkeeping ops via register_op side-effects at import time -- the
        # hooks package has no lazy-skip guard, unlike coordinator_core.ops).
        # One-time-per-invocation cost, in-process, still zero subprocess
        # spawns -- but each hook fire is a fresh process, so this import
        # cost recurs every fire, not just once per session.
        from coordinator_core.hooks import track_dispatched_agents as _op  # noqa: F401
        from coordinator_core.ipc import HookDispatchError, dispatch_from_hook
    except Exception:
        return 0  # engine unimportable -> fail-open

    # scope "common_dir" (coordinator_core/ipc.py _OP_KEY_SCOPE) -- REQUIRED.
    # dispatch_from_hook omits "_origin_worktree" from the envelope entirely
    # when origin_worktree is falsy, matching the prior conditional-set
    # behavior unchanged.
    try:
        dispatch_from_hook(
            "hooks.track_dispatched_agents",
            params,
            origin_worktree=str(cwd) if cwd else None,
        )
    except HookDispatchError:
        return 0  # any engine failure -> fail-open (never brick a hook fire)

    # No stdout relay: this op is MUTATING bookkeeping (dedup/append to
    # dispatched-agents.txt + the em-session-id.txt back-pointer), never
    # advisory -- it always returns no_advisory() == {}. The contract is
    # "stdout NOTHING" (see module docstring), enforced structurally here by
    # never inspecting/relaying the response, not incidentally via `{}`'s
    # falsiness under `if result:`.
    return 0


if __name__ == "__main__":
    sys.exit(main())
