"""provision-sidecar.py — deliberate, flags-in/path-out CLI wrapper around
`coordinator_core.subagent_sandbox.provision_report._provision`.

Purpose: the spawn-time run-report provisioner
(`coordinator_core.subagent_sandbox.provision_report`) is normally invoked by
the `PreToolUse` `matcher: "Agent"` hook at the moment a subagent is
dispatched. That hook is vehicle-gated — a `Workflow` script's `agent()` call
never fires it, so an agent dispatched from inside a Workflow that is
`report_sidecar`-eligible arrives with no sidecar and, per its own contract,
refuses to do any work, at full token cost. Before this CLI existed, the only
way to pre-provision a sidecar for such a spawn was to hand-assemble a JSON
payload for `python3 -m coordinator_core.subagent_sandbox.provision_report`
by reading that module's source. This script is that path made invocable: a
caller (a Workflow script, or any other vehicle that bypasses the hook) runs
it, gets a repo-relative sidecar path on stdout, and injects that path into
the dispatched agent's brief as `sidecar_path:`.

Fail LOUD, not fail-open (deliberate divergence from `provision_report`'s own
contract): `provision_report` sits on the spawn-time hot path and must never
brick a spawn, so it fails open — empty stdout, exit 0, on any ineligible
type, unresolvable git root, or missing session id. This CLI's entire purpose
is the opposite: a deliberate caller who wants a path, and — critically — a
CLEAR ERROR when one can't be produced, so the calling Workflow script (or
its author) learns immediately which precondition failed rather than
discovering a silently-missing `sidecar_path:` several turns later inside a
dispatched agent's refusal. Every failure path below prints a diagnostic
naming the SPECIFIC precondition that failed and exits non-zero.
`provision_report._provision` itself is never modified or weakened to
achieve this — the loudness lives entirely in this wrapper's own
pre-validation and its check of `_provision`'s `None` return.

The provisioning algorithm (payload assembly, path templating, sanitization,
eligibility checking) is not re-implemented here — it is imported and called
exactly once, via `provision_report._provision`, the same entrypoint
`coordinator/bin/fan-out-dispatch.py`'s `_provision_sidecars()` already uses.
The small pieces of resolution logic this CLI ALSO needs
(`_resolve_plugin_root`, `_resolve_claude_klabauter_root_silent`, the DEC-6
`plan_slug.chunk_id` provision-key convention) are imported from
`fan-out-dispatch.py` rather than copy-pasted — see `_load_fan_out_dispatch`
below. `fan-out-dispatch.py`'s own plan-slug derivation was factored into a
standalone `_derive_plan_slug` function to make this import possible without
disturbing that script's byte-for-byte stdout/stderr contract.

Negative-spec: this module never re-implements `_provision`'s sanitization,
path templating, or eligibility check — it only calls the same exported
building blocks `_provision` itself is built from
(`coordinator_core.subagent_sandbox.engine.load_policy` /
`resolve_effective_types` / `resolve_git_root`, and
`provision_report._sanitize_segment`) to produce a diagnostic BEFORE calling
`_provision`, and to explain a `None` return after.

Spec backlink: dispatched via a `coordinator:executor` chunk, 2026-07-30
(provision-sidecar CLI for Workflow-spawned report_sidecar agents).
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from typing import Any, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_fan_out_dispatch() -> Any:
    """Load fan-out-dispatch.py (a dashed filename, not importable as a
    normal module) via `importlib.util`, so this CLI can reuse its
    `_resolve_plugin_root` / `_resolve_claude_klabauter_root_silent` / `PLUGIN_ROOT` /
    `_derive_plan_slug` helpers exactly once rather than duplicating them —
    the named shape this module's docstring calls out to avoid."""
    path = os.path.join(SCRIPT_DIR, "fan-out-dispatch.py")
    spec = importlib.util.spec_from_file_location("_provision_sidecar_fan_out_dispatch", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _resolve_session_id(explicit: Optional[str]) -> str:
    """`--session-id` wins; otherwise the same precedence chain
    `fan-out-dispatch.py`'s `_provision_sidecars` uses: coordinator-set >
    harness-legacy > harness-current."""
    if explicit:
        return explicit
    return (
        os.environ.get("COORDINATOR_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CLAUDE_CODE_SESSION_ID")
        or ""
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="provision-sidecar.py",
        description=(
            "Provision ONE report-sidecar for an agent about to be spawned by a vehicle "
            "that does not traverse the spawn-time provisioning hook (e.g. a Workflow "
            "script's agent() call). Prints the repo-relative sidecar path on stdout and "
            "exits 0 on success; on ANY failure, prints a specific diagnostic to stderr "
            "naming which precondition failed and exits non-zero — never silent."
        ),
    )
    parser.add_argument(
        "--agent-type",
        required=True,
        help="e.g. coordinator:code-reviewer — must be report_sidecar-eligible in policy.",
    )
    parser.add_argument(
        "--provision-key",
        default=None,
        help=(
            "Deterministic key for idempotent re-dispatch; a re-run with the same key "
            "returns the existing path rather than clobbering it. Without it (and without "
            "--plan/--chunk), a random nonce path is used."
        ),
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help=(
            "Defaults to COORDINATOR_SESSION_ID > CLAUDE_SESSION_ID > "
            "CLAUDE_CODE_SESSION_ID."
        ),
    )
    parser.add_argument(
        "--plan",
        default=None,
        help=(
            "Path to the driving plan document. Combined with --chunk (when "
            "--provision-key is not given) to derive a deterministic "
            "provision_key=<plan-slug>.<chunk-id>, mirroring fan-out-dispatch.py's DEC-6 "
            "convention. Also threaded into the underlying payload as plan_path, which "
            "provision_report._provision only acts on for the four G2 plan-pipeline "
            "emitter subagent_types — a no-op for every other agent type."
        ),
    )
    parser.add_argument(
        "--chunk",
        default=None,
        help="Chunk id; only used (with --plan) to derive a provision_key, never sent "
        "as its own payload field (provision_report accepts no such field).",
    )
    parser.add_argument(
        "--type",
        dest="doc_type",
        default=None,
        help="Sidecar template type. Normally OMITTED: the type is resolved from the "
        "policy's report_type_map for the given --agent-type, so the correct template "
        "is the default rather than something the caller must remember. Pass this only "
        "to override that resolution. When neither applies, no type is sent and the "
        "legacy run-report shape is used.",
    )
    parser.add_argument(
        "--policy",
        default=None,
        help="Explicit path to subagent-sandbox-policy.yaml. Defaults to the same "
        "plugin-root resolution fan-out-dispatch.py uses.",
    )
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory to resolve the git root from (defaults to process cwd).",
    )
    return parser


def main(argv: list) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        fod = _load_fan_out_dispatch()
    except Exception as exc:
        _err(f"provision-sidecar.py: ERROR — could not load fan-out-dispatch.py helpers: {exc}")
        return 2

    claude_klabauter_root = fod._resolve_claude_klabauter_root_silent()
    if not claude_klabauter_root or not os.path.isdir(claude_klabauter_root):
        _err(
            "provision-sidecar.py: ERROR — could not resolve the claude-klabauter root "
            "(coordinator_core is unresolvable from this environment)."
        )
        return 2
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)

    try:
        from coordinator_core.subagent_sandbox import provision_report
        from coordinator_core.subagent_sandbox.engine import (
            load_policy,
            resolve_effective_types,
            resolve_git_root,
        )
    except Exception as exc:
        _err(f"provision-sidecar.py: ERROR — could not import provision_report/engine: {exc}")
        return 2

    session_id = _resolve_session_id(args.session_id)
    if not session_id:
        _err(
            "provision-sidecar.py: ERROR — no session id resolved. Pass --session-id or "
            "set one of COORDINATOR_SESSION_ID, CLAUDE_SESSION_ID, CLAUDE_CODE_SESSION_ID."
        )
        return 2

    cwd = args.cwd or os.getcwd()
    git_root = resolve_git_root(cwd)
    if not git_root:
        _err(
            f"provision-sidecar.py: ERROR — could not resolve a git root from cwd: {cwd} "
            "(is this a git working tree?)."
        )
        return 2

    policy_path = args.policy or os.path.join(fod.PLUGIN_ROOT, "subagent-sandbox-policy.yaml")
    if not os.path.isfile(policy_path):
        _err(f"provision-sidecar.py: ERROR — policy file not found: {policy_path}")
        return 2

    try:
        policy = load_policy(policy_path)
    except Exception as exc:
        _err(f"provision-sidecar.py: ERROR — could not load policy at {policy_path}: {exc}")
        return 2

    payload: Dict[str, Any] = {"agent_type": args.agent_type, "session_id": session_id}

    _agent_id, agent_type, subagent_type = resolve_effective_types(payload, git_root)
    is_eligible = agent_type in policy.report_sidecar or subagent_type in policy.report_sidecar
    if not is_eligible:
        _err(
            f"provision-sidecar.py: ERROR — agent type '{args.agent_type}' is not "
            f"report_sidecar-eligible under policy {policy_path}. Eligible types: "
            f"{sorted(policy.report_sidecar)}."
        )
        return 2

    provision_key = args.provision_key
    if not provision_key and args.plan and args.chunk:
        plan_slug = fod._derive_plan_slug(args.plan)
        if not plan_slug:
            _err(
                f"provision-sidecar.py: ERROR — could not derive a plan-slug from --plan: "
                f"{args.plan}"
            )
            return 2
        provision_key = f"{plan_slug}.{args.chunk}"

    if provision_key:
        if provision_report._sanitize_segment(str(provision_key)) is None:
            _err(
                "provision-sidecar.py: ERROR — the resolved provision_key sanitizes to an "
                f"empty/unsafe path segment: {provision_key!r}"
            )
            return 2
        payload["provision_key"] = provision_key

    if provision_report._sanitize_segment(str(session_id)) is None:
        _err(
            "provision-sidecar.py: ERROR — the resolved session id sanitizes to an "
            f"empty/unsafe path segment: {session_id!r}"
        )
        return 2

    if args.plan:
        payload["plan_path"] = args.plan

    # Template-type resolution. Order: explicit --type > report_type_map hit
    # (keyed on agent_type — this CLI's whole input contract is --agent-type;
    # it never sets payload["agent_id"], so resolve_effective_types can never
    # populate subagent_type, and a lookup on it would always miss) > no
    # `type` key at all. The last arm is why this stays a lookup and not a
    # requirement: an absent key leaves the payload type-less, and
    # provision_report._build_doc_text falls through to the frozen legacy
    # run-report shape exactly as it did before this leg existed.
    #
    # Deliberately NOT fail-loud, unlike every other check in this CLI. The
    # loud ones above are preconditions this tool owns and can state
    # definitively (ineligible type, unresolvable session id). Whether a given
    # subagent_type has a report_type_map row is a fact about a policy file
    # the engine repo does not own; refusing on its absence would make this CLI brittle
    # against a sibling's config in exactly the way its own docstring warns
    # against.
    # --type is validated HERE rather than via argparse `choices=`, because
    # TEMPLATE_TYPES lives in provision_report, which this script imports
    # lazily inside main() (after engine-root resolution) -- the parser is
    # built before that import exists. Validating here keeps the two lists in
    # the lockstep TEMPLATE_TYPES' own comment demands, without reintroducing
    # an import-order dependency the lazy import deliberately removed.
    if args.doc_type is not None and args.doc_type not in provision_report.TEMPLATE_TYPES:
        _err(
            f"provision-sidecar.py: ERROR — unknown --type '{args.doc_type}'. "
            f"Valid types: {', '.join(provision_report.TEMPLATE_TYPES)}."
        )
        return 2

    doc_type = args.doc_type or policy.report_type_map.get(agent_type)
    if doc_type:
        payload["type"] = doc_type

    path = provision_report._provision(payload, policy_path, cwd)
    if path is None:
        _err(
            "provision-sidecar.py: ERROR — provision_report._provision returned no path "
            "despite passing every pre-validation check above (eligible agent type, "
            "resolvable git root, non-empty sanitizable session id). This is unexpected — "
            "check for a concurrent policy/engine change."
        )
        return 2

    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
