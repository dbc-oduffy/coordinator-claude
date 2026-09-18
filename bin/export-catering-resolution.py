#!/usr/bin/env python3
"""Re-export coordinator/schemas/subagent-catering-resolution.json from live sources.

Arrival record: state/audits/doe-script-arrivals/W3-C3.yaml
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C3). Mechanical move from DoE-claude
coordinator/bin/export-catering-resolution.py (158 lines, measured cold well under the 200ms
bar -- moved under the batch rules). § Path resolution (docs/plans/2026-09-18-doe-holds-no-scripts.md):
`coordinator/subagent-sandbox-policy.yaml`, `coordinator/snippets/*.md` and
`coordinator/schemas/subagent-catering-resolution.json` are all doctrine-asset class -- they stay
published DoE assets and this script resolves them through the plugin root
(`coordinator_core/warm/caller_context.py :: resolve_caller_context`, falling back to
`coordinator_core/subagent_sandbox/provision_report.py :: resolve_plugin_root` for this bare CLI's
ambient rung, the same idiom `compose-review-wave.py` uses), replacing the DoE version's
`_REPO_ROOT = Path(__file__).resolve().parents[2]` constant -- this script's own tree is no longer
the doctrine tree once it lives in claude-klabauter.

Purpose: the catering-resolution export is a resolve-and-serialize pass over
`coordinator/subagent-sandbox-policy.yaml` and the `coordinator/snippets/` block
files it names, plus `coordinator/snippets/agent-role-dispatched.md`. Claude-klabauter's
Workflow-emit-path catering-payload emitter consumes that file as its SOLE input
for per-agent() catering resolution — it never re-resolves the policy or the
snippets itself — so a stale export is not a test-hygiene problem, it is a live
content-loss window: every emitted dispatch of a drifted subagent_type is catered
with the block list the export last recorded, not the one policy declares today.

Until this script existed the export was refreshed by hand, three times, and each
refresh lagged the policy edit that triggered it by weeks. The refresh trigger is
any change to the policy file or any cited snippet; running this is that refresh.

Hashes and prose are both taken over LF-NORMALIZED content, so this export is
identical from any checkout. That is a deliberate break with what the artifact
recorded through 2026-08-28: every hash up to then was raw working-tree bytes,
which on a Windows checkout meant the policy file hashed LF and every snippet
hashed CRLF. Claude-klabauter's `check_pcli_drift_gate.py :: compute_hash_drift` hashed
raw bytes to match, so the two sides agreed by construction on a same-EOL host —
and a clean Linux clone would have read identical content as drift. Agreed with
Claude-klabauter-em 2026-08-28 to normalize both sides.

THE FLIP IS ORDERED, NOT SYMMETRIC, and this half goes first. While this export
records LF hashes and their gate still hashes raw bytes, leg 3 is red on our
same-EOL hosts for a known reason; their gate flip closes it. Never flip that
gate first — a gate normalized against a raw-byte export manufactures the exact
drift the change exists to prevent, on the one configuration where the two sides
currently agree.

Negative-spec: this script does NOT decide policy. It adds no subagent_type, picks
no block list, and invents no report_type — every value is read from the policy
file. The entry population is the UNION of `report_type_map:` and `contract_blocks:`.
`report_type_map:` alone was used until 2026-09-06 on the belief it was a superset of
both siblings; `coordinator:group-em-assistant` falsified that on 2026-08-30 by
carrying a `contract_blocks:` list while the policy deliberately withholds it from
`report_type_map:`/`report_sidecar:`. Populating from `report_type_map:` alone dropped
its entry entirely, and claude-klabauter's emitter reads this file as its SOLE catering input --
so the declared block went uninjected on every Workflow-emit-path dispatch of that
type. A type present only in `contract_blocks:` serializes `report_type: null` (it has
no declared report type -- that absence is the policy's ruling, not a gap to fill).
An agent type absent from `contract_blocks:` serializes a null block list, exactly
as the hand-maintained export did.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

# Doctrine-asset class relative names (§ Path resolution) -- resolved against the plugin root at
# call time, never against this script's own tree (see module docstring).
_POLICY_REL = "subagent-sandbox-policy.yaml"
_ROLE_FRAMING_REL = "snippets/agent-role-dispatched.md"
_ARTIFACT_REL = "schemas/subagent-catering-resolution.json"

# Repo-relative labels kept for the emitted `source_hashes`/log text, matching the DoE-recorded
# artifact shape byte-for-byte (the export's own consumers key on these exact strings).
_POLICY = "coordinator/subagent-sandbox-policy.yaml"
_ROLE_FRAMING = "coordinator/snippets/agent-role-dispatched.md"
_ARTIFACT = "coordinator/schemas/subagent-catering-resolution.json"


def _ensure_engine_on_path() -> None:
    """Put the engine root on `sys.path`, fail-loud -- the same self-location-first bootstrap
    every other `coordinator/bin/*.py` engine-backed CLI uses. Idempotent."""
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)


def _resolve_plugin_root() -> Optional[str]:
    """Doctrine-asset root for the policy file, the role-framing snippet and the exported
    artifact -- see module docstring's § Path resolution. This script has no per-call payload
    (a bare CLI, not a warm-door op), so `resolve_caller_context()` falls straight through to its
    ambient `resolve_plugin_root` rung, the same idiom `compose-review-wave.py` uses."""
    _ensure_engine_on_path()
    from coordinator_core.warm.caller_context import resolve_caller_context

    return resolve_caller_context().plugin_root


class ExportError(RuntimeError):
    """A fail-loud precondition: an unreachable plugin root. Mirrors
    `compose-review-wave.py`'s `ComposeError` posture for the same doctrine-asset-unreachable
    case -- fail loud, never a silent degrade."""


def _plugin_root() -> Path:
    root = _resolve_plugin_root()
    if not root:
        raise ExportError("coordinator-claude plugin root unreachable")
    return Path(root)


def _read_lf(rel: str) -> str:
    return (_plugin_root() / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


def _sha256_lf(rel: str) -> str:
    return hashlib.sha256(_read_lf(rel).encode("utf-8")).hexdigest()


def build(today: date) -> dict:
    import yaml

    prior = json.loads(_read_lf(_ARTIFACT_REL))
    policy = yaml.safe_load(_read_lf(_POLICY_REL))

    report_type_map = policy["report_type_map"]
    contract_blocks = policy["contract_blocks"]
    eligible = set(policy["report_sidecar"])

    # permission_requirement is a property of the policy file's shape, not of any
    # subagent_type: the file declares no per-type permission field at all. Carried
    # forward verbatim rather than re-derived, so this script never authors doctrine.
    sample = next(iter(prior["entries"].values()))
    permission_requirement = sample["permission_requirement"]
    permission_requirement_note = sample["permission_requirement_note"]

    role_framing = _read_lf(_ROLE_FRAMING_REL)

    entries: dict = {}
    cited: list[str] = []
    for agent_type in sorted(set(report_type_map) | set(contract_blocks)):
        blocks = contract_blocks.get(agent_type)
        resolved = None
        if blocks:
            resolved = []
            for block in blocks:
                source_rel = f"snippets/{block}.md"
                source = f"coordinator/snippets/{block}.md"
                if source not in cited:
                    cited.append(source)
                resolved.append(
                    {"block": block, "source": source, "prose": _read_lf(source_rel)}
                )
        entries[agent_type] = {
            "contract_blocks_resolved": resolved,
            "report_sidecar_eligible": agent_type in eligible,
            "report_type": report_type_map.get(agent_type),
            "permission_requirement": permission_requirement,
            "permission_requirement_note": permission_requirement_note,
            "role_framing_resolved": role_framing,
        }

    source_hashes = {_POLICY: _sha256_lf(_POLICY_REL)}
    for source in cited:
        source_hashes[source] = _sha256_lf(source[len("coordinator/"):])
    source_hashes[_ROLE_FRAMING] = _sha256_lf(_ROLE_FRAMING_REL)

    return {
        "$comment": prior["$comment"],
        "artifact": prior["artifact"],
        "version": prior["version"],
        "generated_at": today.isoformat(),
        "hash_algorithm": prior["hash_algorithm"],
        "source_hashes": source_hashes,
        "entries": entries,
    }


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the on-disk export differs from a fresh one; write nothing",
    )
    args = parser.parse_args(argv)

    try:
        fresh = build(date.today())
    except ExportError as exc:
        print(f"export-catering-resolution: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(fresh, indent=2, ensure_ascii=False) + "\n"
    target = _plugin_root() / _ARTIFACT_REL

    if args.check:
        on_disk = json.loads(_read_lf(_ARTIFACT_REL))
        drifted = {k: v for k, v in fresh.items() if k != "generated_at"}
        if all(on_disk.get(k) == v for k, v in drifted.items()):
            print("catering-resolution export is current")
            return 0
        print("catering-resolution export is STALE — run this script without --check")
        return 1

    target.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {_ARTIFACT} ({len(fresh['entries'])} entries, "
          f"{len(fresh['source_hashes'])} source hashes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
