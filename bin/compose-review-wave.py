#!/usr/bin/env python3
"""compose-review-wave.py -- caller-side composer for the fired review
partition workflow.

Arrival record: state/audits/doe-script-arrivals/W2-C10.yaml
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C10). Mechanical
move from DoE-claude coordinator/bin/compose-review-wave.py (809 lines,
measured cold at ~180ms -- under the 200ms bar, moved under the batch
rules unchanged in behavior). `coordinator/docs/wiki/workflow-emitter-contract.md`
§5 pins a four-part payload on every Workflow-emit agent-call. A Workflow
`agent()` spawn is not an `Agent`-tool call, so DoE's
`coordinator/hooks/scripts/enforce-agent-dispatch-mode.py` PreToolUse
catering never fires on it. This script is the caller-side reconstruction
of the three parts a resident composer CAN close (i, ii, iv) -- part (iii),
the permission-mode requirement, is a settled unclosable residual on this
path (§6) and is recorded, not resolved, here.

Sibling to DoE's coordinator/workflows/wsc-review-partition.mjs: this script
produces exactly the `args` object that Workflow script consumes --
`{ slices: [ { id, diffPath, shaRange, wasteReport,
reviewer: {sidecarPath, contractBlocks}, integrator: {sidecarPath, contractBlocks} } ] }`,
no other top-level or per-role key. `wasteReport` is a repo-relative path to the
slice's attributed waste report (see `_run_waste_attribution`/`_write_waste_report`
below).

INVERTS the hook's fail-open posture, deliberately. The hook fails open on
a missing contract block because a missing block must never block a spawn
that is already happening; this composer runs BEFORE the spawn, so a
missing block here means the fired reviewer would arrive uncatered --
every failure leg below exits non-zero with a named stderr precondition
instead of degrading silently. Two of the hook's own tolerances do NOT
carry over for the same reason: no `timeout=2` on the provision_report
subprocess call (a cold interpreter start on this box will not reliably
land inside that budget, and this script has no dispatch deadline to
race), and the engine-root resolution leg is trivial here -- this script
runs from inside the engine's own tree, so no ambient probe is needed for
it (see § Path resolution below).

Resolves catering parts (i) resolved contract_blocks prose and (ii) the
pre-allocated run-report sidecar path LIVE, via one
`python -m coordinator_core.subagent_sandbox.provision_report` subprocess
per phase -- the same invocation shape the dispatch hook already uses,
with an explicit `--policy` flag and a stdin payload carrying top-level
`agent_type`, `provision_key`, and `contract_blocks`. Part (iv), the
resolved role-framing prose (`snippets/agent-role-dispatched.md`, verbatim,
unconditional, no roster lookup), has no roster to resolve against and is
appended directly by this script, not via provision_report.

`provision_key` is `wsc-<run-id>.<slice-id>.<role>` -- deterministic (given
the same `--run-id`, a re-run returns the same path rather than clobbering)
and slice-bearing (N concurrent same-type sidecars are distinguishable by
filename alone). `--run-id` is a REQUIRED argument, not a wall-clock
default: minting a fresh timestamp on every invocation would make a
same-manifest re-run non-idempotent by construction. The caller (the
`/workstream-complete` ceremony, or a test) mints one run-id once and
reuses it across every composer invocation for that run.

Contract-block names come from `contract_blocks:` in the policy file, read
with a real `yaml.safe_load` -- never a hardcoded list or count.

§ Path resolution (docs/plans/2026-09-18-doe-holds-no-scripts.md). Three
DoE-relative paths this script used to derive from `_engine_root`/its own
`__file__` parent chain, now resolved per class:
  - engine: `coordinator_core` itself -- this module's own tree
    (`Path(__file__).parents[2]` IS the engine root here; no ambient probe,
    no `_engine_root` import).
  - doctrine asset: `subagent-sandbox-policy.yaml` and
    `snippets/agent-role-dispatched.md` -- both stay published DoE assets,
    resolved through the plugin root
    (`coordinator_core/warm/caller_context.py :: resolve_caller_context`,
    which falls back to `coordinator_core/subagent_sandbox/provision_report.py
    :: resolve_plugin_root` when no per-call payload is available, as is the
    case for this bare CLI).
  - session repo: `state/review-trail/...` outputs and the manifest/diff
    inputs -- the caller's cwd, unchanged from DoE's version.

Windows-first: `subprocess.run` with an argv list, `shell=False` throughout
-- `waste-signal.py`'s attribution child is spawned via `sys.executable`,
never a bare interpreter name. Diff-freezing no longer spawns at all:
`_freeze_slices_batch` calls `coordinator_core.ops.review_freeze_diff.
freeze_diffs_batch` in-process, once per compose() call, for every slice
lacking a pre-frozen `diffPath` -- see that function's own docstring for the
single-git-spawn-per-phase batching this replaces the one-CLI-spawn-per-slice
shape with. `pathlib` throughout; every path in the emitted JSON is
repo-relative.

CLI:
    python coordinator/bin/compose-review-wave.py \\
        --manifest <path-to-slice-manifest.json> \\
        --run-id <YYYYMMDD-HHMMSS>
        [--policy <path-to-subagent-sandbox-policy.yaml>]

Manifest shape (JSON):
    { "slices": [ { "id": "<slice-id>", "diffPath": "<repo-relative-path>" }
                   | { "id": "<slice-id>", "range": "<git-range>" }, ... ] }

A slice entry carries EITHER a pre-frozen `diffPath` (passed through
verbatim) OR a `range`, which this script freezes itself by delegating to
the installed `freeze-review-diff` CLI -- never by reimplementing it.

Output on stdout: ONE JSON object, the literal `args` payload for the
Workflow review-partition script's consumer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_COORDINATOR_ROOT = _SCRIPT_DIR.parent
_REPO_ROOT = _COORDINATOR_ROOT.parent
_WASTE_SIGNAL_SCRIPT = _SCRIPT_DIR / "waste-signal.py"

#: Wall-clock ceiling for one slice's attribution child. Generous relative to a
#: normal covering-test run; it exists to bound a HANG, not to police slow tests.
_WASTE_ATTRIBUTION_TIMEOUT_S = 600


def _ensure_engine_on_path() -> None:
    """Put the engine root on `sys.path`, fail-loud -- the same
    self-location-first bootstrap every other `coordinator/bin/*.py`
    engine-backed CLI uses (see e.g. `coordinator/bin/workweek-complete-brief.py`).
    Idempotent: `require_colocated_engine_on_path` front-inserts onto
    `sys.path` and a second call is harmless."""
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)


def _resolve_plugin_root() -> Optional[str]:
    """Doctrine-asset root for `subagent-sandbox-policy.yaml` and
    `snippets/agent-role-dispatched.md` -- see module docstring's
    § Path resolution. This script has no per-call payload (it is a bare
    CLI, not a warm-door op), so `resolve_caller_context()` falls straight
    through to its ambient `resolve_plugin_root` rung."""
    _ensure_engine_on_path()
    from coordinator_core.warm.caller_context import resolve_caller_context

    return resolve_caller_context().plugin_root


class ComposeError(RuntimeError):
    """A fail-loud precondition. `main()` prints `str(exc)` to stderr and
    exits non-zero -- never a silent degrade, per this module's whole
    inverted-posture rationale (see module docstring)."""


def _load_role_append() -> str:
    """Part (iv): the resolved role-framing prose, read verbatim from its
    canonical snippet source. A missing plugin root or a missing snippet
    is a hard configuration break -- routed through ComposeError,
    fail-loud like everything else here."""
    plugin_root = _resolve_plugin_root()
    if not plugin_root:
        raise ComposeError("coordinator-claude plugin root unreachable")
    role_snippet = Path(plugin_root) / "snippets" / "agent-role-dispatched.md"
    try:
        return role_snippet.read_text(encoding="utf-8").strip()
    except Exception as exc:
        raise ComposeError(
            f"agent-role-dispatched snippet unreadable at {role_snippet}: {exc}"
        ) from exc


def _resolve_policy_file(explicit_policy: Optional[Path]) -> Path:
    """`--policy` wins if given; otherwise resolves against the plugin
    root (doctrine-asset class -- see module docstring)."""
    if explicit_policy is not None:
        return explicit_policy
    plugin_root = _resolve_plugin_root()
    if not plugin_root:
        raise ComposeError("coordinator-claude plugin root unreachable")
    return Path(plugin_root) / "subagent-sandbox-policy.yaml"


def _load_policy(policy_file: Path) -> dict:
    import yaml

    try:
        text = policy_file.read_text(encoding="utf-8")
    except Exception as exc:
        raise ComposeError(
            f"subagent-sandbox-policy.yaml unreadable at {policy_file}: {exc}"
        ) from exc
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        raise ComposeError(
            f"subagent-sandbox-policy.yaml malformed at {policy_file}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ComposeError(
            f"subagent-sandbox-policy.yaml at {policy_file} did not parse to a mapping"
        )
    return data


def _contract_block_names(policy: dict, agent_type: str) -> list[str]:
    """Ordered block-name list for `agent_type`, read from `contract_blocks:`.

    A real `yaml.safe_load` result, never a hardcoded list or count (today
    that resolves to three blocks for coordinator:code-reviewer and four
    for coordinator:review-integrator -- this function must not encode
    either number). A structurally absent `contract_blocks:` MAPPING is a
    malformed policy and fails loud; an absent or non-list entry for one
    `agent_type` fails open to `[]`, mirroring the policy file's own
    documented lookup-miss contract -- an empty block list then surfaces
    downstream as a missing `injected_prompt_blocks` key from
    provision_report, which `_provision_phase` below already treats as a
    fail-loud precondition.
    """
    contract_blocks = policy.get("contract_blocks")
    if not isinstance(contract_blocks, dict):
        raise ComposeError("policy carries no contract_blocks: mapping")
    names = contract_blocks.get(agent_type)
    if not isinstance(names, list):
        return []
    return [name for name in names if isinstance(name, str)]


def _resolve_report_type(policy: dict, agent_type: str) -> str:
    """Mirror the hook's Concern B.1: subagent_type -> template type via
    `report_type_map:`. Fail-open to "" (no --type flag; provision_report's
    own default applies) on any absent/malformed mapping -- matching the
    hook's own tolerance for this leg exactly, since an unmapped identity
    getting the default template is not itself a catering failure."""
    report_type_map = policy.get("report_type_map")
    if not isinstance(report_type_map, dict):
        return ""
    report_type = report_type_map.get(agent_type)
    return report_type if isinstance(report_type, str) else ""



def _repo_relative(path_str: str) -> str:
    """Normalize an emitted path to repo-relative POSIX form.

    The emitted args object is consumed by a Workflow script and handed to
    dispatched phases, so every path in it must be repo-relative: an absolute
    path bakes THIS checkout's root into the payload, which makes a composed
    wave non-portable and non-reproducible on any other host or clone.

    Applied at the emission chokepoint rather than trusting each producer.
    `freeze-review-diff` prints an absolute path on this box despite its
    contract saying otherwise, and a pass-through `diffPath` comes from a
    caller-authored manifest that this script does not control -- normalizing
    where the value enters the payload covers both without either producer
    having to be trusted.
    """
    candidate = Path(path_str)
    if not candidate.is_absolute():
        return PurePosixPath(candidate.as_posix()).as_posix()
    try:
        return candidate.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except ValueError:
        # Genuinely outside the repo -- emitting a wrong relative path would be
        # worse than an honest absolute one.
        return candidate.as_posix()


def _freeze_slices_batch(requests: list[dict[str, str]]) -> list[dict]:
    """Freeze every slice in `requests` (each `{"slice_id": ..., "range": ...}`)
    via ONE in-process call to `coordinator_core.ops.review_freeze_diff.
    freeze_diffs_batch` -- never the `freeze-review-diff` CLI, and never one
    call per slice (that per-slice CLI spawn was amplification site
    `compose:649` in the pre-batch inventory; this function's only caller,
    `compose()`, calls it exactly once, outside its per-slice loop).

    Returns `freeze_diffs_batch`'s own result list, same order as `requests`
    -- `compose()` maps each entry back onto its slice and raises
    `ComposeError` (this module's own fail-loud posture) on any per-request
    `error`, rather than this function doing it, so the one ComposeError
    wording for "which slice, what precondition" lives in one place.

    Module-scope inert per this module's own bootstrap convention -- the
    import happens here, not at module import time, matching every other
    `coordinator_core`-reaching function in this file.

    NO TRAIL RECORD IS REQUESTED, and its absence is not a gap. `review_trail.
    write` was gravestoned at kill-ledger K-060 (2026-08-27, DoE-claude) and
    the engine's CLI has no legacy fallback by design.

    The sha-range binding it protected did not depend on it. This slice's
    range reaches the reviewer as the manifest's own `shaRange`, and the
    reviewer attests `reviewed_range` into its sidecar -- which, per
    `artifact-shape-contract.schema.json`, "ADMITS, NEVER REPLACES" a trail
    record and "does not duplicate or re-implement" it. The attestation was
    always the binding; the trail record was a separate artifact it admitted.
    With nothing written, there is nothing to admit, and nothing else changes.
    """
    _ensure_engine_on_path()
    from coordinator_core.ops.review_freeze_diff import freeze_diffs_batch

    try:
        return freeze_diffs_batch(_REPO_ROOT, requests)
    except Exception as exc:
        raise ComposeError(f"freeze_diffs_batch failed for this wave: {exc}") from exc


def _provision_key(run_id: str, slice_id: str, role: str) -> str:
    return f"wsc-{run_id}.{slice_id}.{role}"


#: role -> subagent_type, the two phases every slice gets.
_ROLE_AGENT_TYPE = {
    "reviewer": "coordinator:code-reviewer",
    "integrator": "coordinator:review-integrator",
}

#: The exact per-slice key set this composer emits -- pinned against the
#: consuming Workflow script's shape (see module docstring). `wasteReport`
#: is a repo-relative path to the slice's attributed waste report (see
#: `_write_waste_report` below), never an inline dict, matching every other
#: artifact key in this set.
_SLICE_KEYS = {"id", "diffPath", "reviewer", "integrator", "wasteReport"}
_ROLE_PAYLOAD_KEYS = {"sidecarPath", "contractBlocks"}

#: Matches a git unified-diff file header, e.g. "diff --git a/foo.py b/foo.py".
#: The b/ (post-image) side is the changed repo-relative path this composer
#: attributes against -- reliable even for a deletion (whose "+++" line reads
#: "/dev/null") because the "diff --git" header always names both sides by
#: their tree path, never /dev/null.
_DIFF_GIT_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")


def _provision_phase(
    *,
    policy_file: Path,
    agent_type: str,
    session_id: str,
    provision_key: str,
    contract_block_names: list[str],
    report_type: str,
) -> tuple[str, str]:
    """One IN-PROCESS call resolving BOTH catering parts (i) resolved
    contract_blocks prose and (ii) the pre-allocated sidecar path for a
    single phase -- `provision_report._provision` /
    `assemble_contract_blocks_for_payload` directly, the same functions the
    `python -m coordinator_core.subagent_sandbox.provision_report` CLI this
    replaced called as its own last step (Review: overengineering-reviewer,
    Finding 1). No cold interpreter, no `PYTHONPATH` env splice: this module
    already lives inside the engine's own tree (`_ensure_engine_on_path`),
    so `coordinator_core` is importable directly. `main()`'s own `--type`
    default ("run-report", applied only when the payload doesn't already
    carry one) is mirrored here rather than inherited, since there is no CLI
    arg parser in this path to apply it for us.

    Any failure leg here (either function raising, either output value
    missing) is a ComposeError -- fail loud, never fail open, per this
    module's inverted posture."""
    _ensure_engine_on_path()
    from coordinator_core.subagent_sandbox.provision_report import (
        _provision,
        assemble_contract_blocks_for_payload,
    )

    payload: dict[str, Any] = {
        "session_id": session_id,
        "agent_type": agent_type,
        "provision_key": provision_key,
        "type": report_type or "run-report",
    }
    if contract_block_names:
        payload["contract_blocks"] = contract_block_names

    try:
        sidecar_path = _provision(payload, str(policy_file), None)
    except Exception as exc:
        raise ComposeError(
            f"provision_report._provision failed for {agent_type}/{provision_key}: {exc}"
        ) from exc

    try:
        injected_blocks = assemble_contract_blocks_for_payload(
            payload, cwd=None, report_sidecar_path=sidecar_path
        )
    except Exception as exc:
        raise ComposeError(
            f"provision_report.assemble_contract_blocks_for_payload failed for "
            f"{agent_type}/{provision_key}: {exc}"
        ) from exc

    if not isinstance(sidecar_path, str) or not sidecar_path:
        raise ComposeError(
            f"provision_report returned no report_sidecar for {agent_type}/{provision_key} "
            "-- reviewer would arrive uncatered"
        )
    if not isinstance(injected_blocks, str) or not injected_blocks:
        raise ComposeError(
            f"provision_report returned no injected_prompt_blocks for {agent_type}/{provision_key} "
            "-- a contract block could not be assembled"
        )

    return sidecar_path, injected_blocks


def _changed_paths_from_diff(diff_path: Path) -> list[str]:
    """Derive the changed repo-relative POSIX paths from a slice's own frozen
    diff: "COMPUTE PER SLICE, FROM THE SLICE'S OWN DIFF."

    Reads `diff --git a/X b/Y` headers only -- the one line every unified
    diff carries for every touched file (add, modify, delete, rename alike)
    that always names a real tree path on both sides, unlike `+++`/`---`
    which read `/dev/null` for an add or a delete. An unreadable or
    diff-less file returns an empty list, which the caller treats as
    "no executable surface" (the not-measurable case), never a crash.
    """
    try:
        text = diff_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    paths: set[str] = set()
    for line in text.splitlines():
        match = _DIFF_GIT_HEADER.match(line)
        if match:
            paths.add(PurePosixPath(match.group(2)).as_posix())
    return sorted(paths)


def _not_measurable_attribution(reason: str) -> dict:
    """The shared not-measurable shape this composer emits whenever it
    cannot even reach `waste-signal.py --attribute-diff` -- mirrors
    `AttributedWasteReport`'s own `as_report()` keys (the composer parses
    the instrument's shape, it does not invent a competing one) plus
    `resolved_tests`, always `[]` here since no child process ever ran."""
    return {
        "status": "not-measurable",
        "reason": reason,
        "attributable_redundant_opens": 0,
        "attributable_paths": [],
        "elsewhere_in_repo_redundant_opens": 0,
        "out_of_repo_redundant_opens": 0,
        "basis": None,
        "resolved_tests": [],
    }


def _extract_trailing_json_object(text: str) -> Optional[dict]:
    """Recover the JSON object `waste-signal.py --attribute-diff` prints as
    the LAST thing on its stdout, even when a resolved covering test's own
    `pytest.main()` run has already written its console report to the SAME
    stream ahead of it (measured live: `pytest.main()` writes its report to
    real `sys.stdout` before `run_attribute_diff` returns, so a subprocess
    pipe interleaves both onto one fd -- `json.loads(stdout)` on the whole
    capture then fails even on a clean, successful run).

    Defensive trailing-object extraction -- never a change to how
    `waste-signal.py` itself prints. Returns `None` (never raises) if no
    suffix of the output
    parses as a JSON object, which the caller folds into the same
    not-measurable path as every other unparseable-output case."""
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() != "{":
            continue
        candidate = "\n".join(lines[i:])
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _run_waste_attribution(changed_paths: list[str], repo_root: Path) -> dict:
    """Spawn `waste-signal.py --attribute-diff <changed_paths>` as this
    composer's OWN CHILD and parse its printed JSON: "ARM THE HOOK IN THE
    SAME PROCESS AS THE TESTS -- AND MAKE THAT PROCESS A CHILD". The
    instrument arms `sys.addaudithook` and runs the resolved covering
    tests inside ONE process (visibility), while this composer never runs a
    test suite in its own process (crash isolation, per
    coordinator/docs/wiki/test-environment-discipline.md:161/168). This
    composer hosts no test-running logic of its own -- it names the child's
    stdout and parses it; the instrument owns test resolution, hook arming,
    and running.

    A missing executable surface (no changed paths at all -- the common case,
    since only ~14% of this repo's commits touch a `.py`) short-circuits
    before spawning: `--attribute-diff` requires at least one path argument,
    so there is nothing to hand it. A non-zero child return code, an
    unspawnable child, or unparseable stdout all degrade to the SAME
    not-measurable shape with the returncode/reason folded in -- this is
    NOT a `ComposeError`: unlike this module's fail-loud structural
    preconditions (policy, plugin root, contract blocks), a measurement
    that could not be taken is itself the honest answer, not a reason to
    abort composing the review payload.
    """
    if not changed_paths:
        return _not_measurable_attribution(
            "diff carried no parseable changed paths -- no executable surface to attribute against"
        )

    argv = [sys.executable, str(_WASTE_SIGNAL_SCRIPT), "--attribute-diff", *changed_paths]

    # The child runs the slice's own covering tests, which is branch code this
    # gate does not yet trust. Give it a scratch HOME/TMP so a test writing to
    # a user-level config or dotfile cannot mutate the tree being reviewed --
    # the isolation this script's Anti-scope promises, and the HOME-capture
    # hazard test-environment-discipline.md sec.4 records. cwd stays
    # repo_root: the child resolves repo-relative paths against it, and a
    # scratch cwd would break attribution rather than isolate anything.
    with tempfile.TemporaryDirectory(prefix="waste-attr-") as scratch:
        child_env = dict(os.environ)
        child_env["HOME"] = scratch
        child_env["USERPROFILE"] = scratch
        child_env["TMPDIR"] = scratch
        child_env["TEMP"] = scratch
        child_env["TMP"] = scratch
        try:
            proc = subprocess.run(
                argv,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                env=child_env,
                timeout=_WASTE_ATTRIBUTION_TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            # A hung covering test must degrade to not-measurable, never block the
            # review wave -- an unbounded wait here is the "review gate dies with
            # the reviewer's payload" failure the child-process design exists to
            # prevent, arriving by hang instead of by crash.
            return _not_measurable_attribution(
                f"waste-signal --attribute-diff exceeded {_WASTE_ATTRIBUTION_TIMEOUT_S}s and was killed"
            )
        except Exception as exc:
            return _not_measurable_attribution(f"waste-signal --attribute-diff failed to spawn: {exc}")

    parsed: Optional[dict] = None
    if proc.returncode == 0:
        try:
            candidate = json.loads(proc.stdout)
            if isinstance(candidate, dict):
                parsed = candidate
        except Exception:
            parsed = _extract_trailing_json_object(proc.stdout or "")

    if parsed is None:
        return _not_measurable_attribution(
            f"waste-signal --attribute-diff exited {proc.returncode} with no parseable JSON on "
            f"stdout: {(proc.stderr or '').strip()[:500]}"
        )

    attribution = parsed.get("attribution")
    if not isinstance(attribution, dict):
        return _not_measurable_attribution(
            "waste-signal --attribute-diff printed JSON with no 'attribution' object"
        )

    rendered = dict(attribution)
    rendered["resolved_tests"] = parsed.get("resolved_tests", [])
    return rendered


def _write_waste_report(report: dict, run_id: str, slice_id: str) -> Path:
    """Persist the slice's attributed waste report to a deterministic,
    slice-and-run-scoped path -- the FILE this composer emits under the
    `wasteReport` key (a path, like `diffPath`, never an inline
    dict -- see `_SLICE_KEYS`'s own comment)."""
    out_dir = _REPO_ROOT / "state" / "review-trail" / "waste-reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.{slice_id}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return out_path


def _slice_attribution_view(union_attribution: dict, slice_paths: set[str]) -> dict:
    """Narrow ONE union-wide `waste-signal.py --attribute-diff` result (run
    over every slice's changed paths combined -- see `compose()`'s own
    docstring for why this replaced amplification site `compose:658`) down
    to the view for `slice_paths` alone: "give each slice the attribution for
    its own paths" (module docstring).

    `attributable_paths`/`attributable_redundant_opens` (dynamic) and
    `static.per_path` are PER-PATH -- `AttributedWasteReport.as_report()` and
    `StaticWasteReport.as_report()` both key their per-path breakdown by
    path (coordinator/bin/waste-signal.py), so filtering to `path in
    slice_paths` and re-summing `attributable_redundant_opens` from the
    filtered list is exact, not an approximation.

    `elsewhere_in_repo_redundant_opens`/`out_of_repo_redundant_opens`/
    `status`/`reason`/`basis` and `static`'s own `duplicate_groups`/
    `dropped_count`/`call_status`/`hint` stay as the union computed them --
    they were already aggregate, run-scoped facts under the pre-batch
    per-slice call (each slice's own `_run_waste_attribution` reported them
    for ITS OWN changed-path set only; sharing one union-wide value across
    every slice is the one axis this restructuring changes, and it is
    unavoidable without re-running the instrument per slice, exactly the
    amplification this change exists to remove)."""
    view = dict(union_attribution)

    attributable_paths = [
        entry
        for entry in union_attribution.get("attributable_paths", [])
        if isinstance(entry, dict) and entry.get("path") in slice_paths
    ]
    view["attributable_paths"] = attributable_paths
    view["attributable_redundant_opens"] = sum(
        entry.get("redundant_opens", 0) for entry in attributable_paths
    )

    static = union_attribution.get("static")
    if isinstance(static, dict):
        static_view = dict(static)
        per_path = static.get("per_path")
        if isinstance(per_path, dict):
            static_view["per_path"] = {
                path: entry for path, entry in per_path.items() if path in slice_paths
            }
        view["static"] = static_view

    return view


def compose(
    manifest: dict,
    *,
    run_id: str,
    session_id: str,
    policy_file: Optional[Path] = None,
) -> dict:
    """Compose the args object. Raises ComposeError on any missing
    precondition -- see module docstring."""
    resolved_policy_file = _resolve_policy_file(policy_file)
    policy = _load_policy(resolved_policy_file)
    role_append = _load_role_append()

    slices_in = manifest.get("slices")
    if not isinstance(slices_in, list) or not slices_in:
        raise ComposeError("manifest carries no slices")

    # The sidecar directory MUST be the session the fired phases actually run
    # under, never a synthetic one. `provision_report` resolves a sidecar to
    # `.coordinator-local/subagent-share/<session_id>/<provision_key>.md`, and the Edit
    # confinement guard confines every agent's writes to the directory named by
    # its OWN runtime session id. A workflow-spawned phase inherits the EM's
    # session, so a composed-in `wsc-<run_id>` directory is one no fired phase
    # can write to: the reviewer reads its provisioned scaffold, is denied on
    # write, and the integrator downstream correctly refuses an unfilled
    # sidecar. Measured live on DoE-claude -- run wf_1800c597-781 lost all five
    # slices this way. Slice-bearing uniqueness lives in `provision_key` (the
    # FILENAME), which is what the shared-sidecar requirement actually needs,
    # so nothing is lost by dropping the per-run directory.

    # Pass 1: validate every slice entry and resolve its range/diffPath.
    # Slices lacking a pre-frozen `diffPath` are collected here, never frozen
    # inline -- amplification site `compose:649` (one `freeze-review-diff`
    # CLI spawn per slice) is closed by freezing the whole collected set in
    # ONE call after this loop, not inside it (module docstring).
    slice_ids: list[str] = []
    range_specs: list[str] = []
    diff_paths: list[Optional[str]] = []
    freeze_requests: list[dict[str, str]] = []
    freeze_positions: list[int] = []

    for slice_entry in slices_in:
        if not isinstance(slice_entry, dict):
            raise ComposeError("a slice entry is not a JSON object")

        slice_id = slice_entry.get("id")
        if not isinstance(slice_id, str) or not slice_id:
            raise ComposeError("a slice entry is missing its id")

        # A slice must name the sha range it covers whether or not it also
        # supplies a pre-frozen diff. `reviewed_range` is writable ONLY by the
        # reviewing subagent (artifact-shape-contract.schema.json), so a range
        # that never reaches the reviewer's payload can never be attested by
        # anyone -- and the attestation is the whole binding, since
        # review_trail.write was gravestoned at K-060.
        range_spec = slice_entry.get("range")
        if not isinstance(range_spec, str) or not range_spec:
            raise ComposeError(
                f"slice {slice_id!r} carries no range -- a pre-frozen diffPath does "
                "not substitute for it, because the reviewer cannot attest a "
                "reviewed_range it was never given"
            )

        slice_ids.append(slice_id)
        range_specs.append(range_spec)

        diff_path = slice_entry.get("diffPath")
        if isinstance(diff_path, str) and diff_path:
            diff_paths.append(diff_path)
        else:
            diff_paths.append(None)
            freeze_positions.append(len(diff_paths) - 1)
            freeze_requests.append({"slice_id": slice_id, "range": range_spec})

    if freeze_requests:
        freeze_results = _freeze_slices_batch(freeze_requests)
        for pos, result in zip(freeze_positions, freeze_results):
            slice_id = slice_ids[pos]
            if result.get("error"):
                raise ComposeError(
                    f"freeze_diffs_batch failed for slice {slice_id!r}: {result['error']}"
                )
            frozen_path = result.get("diff_path")
            if not isinstance(frozen_path, str) or not frozen_path:
                raise ComposeError(
                    f"freeze_diffs_batch produced no diff_path for slice {slice_id!r} -- "
                    "the reviewer would arrive with nothing to review"
                )
            diff_paths[pos] = frozen_path

    # Pass 2: derive every slice's changed paths from its OWN frozen diff
    # (pure file reads -- no spawn), then attribute the UNION of every
    # slice's changed paths in ONE `waste-signal.py --attribute-diff` child
    # -- amplification site `compose:658` (one child per slice) is closed by
    # running the instrument once over the combined set and splitting its
    # per-path result back out per slice (`_slice_attribution_view`), never
    # by re-running it per slice.
    changed_paths_by_slice: list[list[str]] = []
    union_paths: set[str] = set()
    for diff_path in diff_paths:
        assert isinstance(diff_path, str) and diff_path  # pass 1 guarantees this
        diff_path_obj = Path(diff_path)
        if not diff_path_obj.is_absolute():
            diff_path_obj = _REPO_ROOT / diff_path_obj
        changed_paths = _changed_paths_from_diff(diff_path_obj)
        changed_paths_by_slice.append(changed_paths)
        union_paths.update(changed_paths)

    union_attribution = _run_waste_attribution(sorted(union_paths), _REPO_ROOT)

    slices_out: list[dict[str, Any]] = []
    for idx, slice_id in enumerate(slice_ids):
        range_spec = range_specs[idx]
        diff_path = diff_paths[idx]
        changed_paths = changed_paths_by_slice[idx]

        waste_attribution = _slice_attribution_view(union_attribution, set(changed_paths))
        waste_report_path = _write_waste_report(
            {"changed_paths": changed_paths, "attribution": waste_attribution},
            run_id,
            slice_id,
        )

        role_payloads: dict[str, dict[str, str]] = {}
        for role, agent_type in _ROLE_AGENT_TYPE.items():
            block_names = _contract_block_names(policy, agent_type)
            report_type = _resolve_report_type(policy, agent_type)
            provision_key = _provision_key(run_id, slice_id, role)
            sidecar_path, injected_blocks = _provision_phase(
                policy_file=resolved_policy_file,
                agent_type=agent_type,
                session_id=session_id,
                provision_key=provision_key,
                contract_block_names=block_names,
                report_type=report_type,
            )
            # Parts (i) and (iv) concatenated, role framing LAST -- see
            # module docstring and DoE-claude's coordinator/hooks/scripts/
            # enforce-agent-dispatch-mode.py's own ordering
            # (sidecar offer -> injected contract -> role framing).
            contract_blocks_text = injected_blocks.rstrip("\n") + "\n\n" + role_append
            role_payloads[role] = {
                "sidecarPath": sidecar_path,
                "contractBlocks": contract_blocks_text,
            }

        slices_out.append(
            {
                "id": slice_id,
                "diffPath": _repo_relative(diff_path),
                # The reviewer attests `shaRange` into its sidecar's
                # `reviewed_range`; nothing downstream can supply it on the
                # reviewer's behalf, and review_trail.write gates on it.
                "shaRange": range_spec,
                "wasteReport": _repo_relative(str(waste_report_path)),
                "reviewer": role_payloads["reviewer"],
                "integrator": role_payloads["integrator"],
            }
        )

    return {"slices": slices_out}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--run-id",
        required=True,
        help="Stable run identifier, e.g. YYYYMMDD-HHMMSS. Reused across "
        "every composer invocation for one run -- see module docstring on "
        "why this is required, never wall-clock-defaulted.",
    )
    parser.add_argument(
        "--session-id",
        required=True,
        help="The session id the FIRED phases will run under -- for a workflow "
        "spawn that is the EM's own session, since a workflow-spawned agent "
        "inherits it. Required, never synthesized: the Edit confinement guard "
        "confines each agent's writes to .coordinator-local/subagent-share/<its own "
        "session id>/, so a sidecar provisioned anywhere else is one no fired phase "
        "can write to, and the wave is lost on the integrator leg.",
    )
    parser.add_argument(
        "--policy",
        default=None,
        type=Path,
        help="Explicit subagent-sandbox-policy.yaml path. Defaults to the "
        "coordinator-claude plugin root's copy (doctrine-asset class -- see "
        "module docstring's § Path resolution).",
    )
    args = parser.parse_args(argv)

    try:
        manifest_text = args.manifest.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"compose-review-wave: manifest unreadable at {args.manifest}: {exc}", file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_text)
    except Exception as exc:
        print(f"compose-review-wave: manifest not valid JSON at {args.manifest}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(manifest, dict):
        print(f"compose-review-wave: manifest at {args.manifest} is not a JSON object", file=sys.stderr)
        return 1

    try:
        result = compose(
            manifest,
            run_id=args.run_id,
            session_id=args.session_id,
            policy_file=args.policy,
        )
    except ComposeError as exc:
        print(f"compose-review-wave: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(json.dumps(result))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
