"""Run-folder contract and stage registry for artifact-investigation gate scripts.

Every stage writes one JSON file in a single run folder; the gates read those files.
Stdlib only. `STAGES` is the one place a stage flips to landed.
"""

import json
from pathlib import Path

# (stage_id, cluster, landed). A sibling stage stays landed=False until its
# primitive publishes; the judgment stage needs no sibling.
STAGES = (
    ("parse-ingest", "C16+C5", False),
    ("index-query", "C4", False),
    ("record-claims", "C3", False),
    ("judgment", "none", True),
)

PRIORITIES = ("must", "should", "could")
REQUIREMENTS_FILE = "requirements.json"


def stage_ids():
    return tuple(s[0] for s in STAGES)


def is_landed(stage):
    """True when `stage` is landed; raises ValueError on an unknown stage."""
    for sid, _cluster, landed in STAGES:
        if sid == stage:
            return landed
    raise ValueError(f"unknown stage: {stage!r}")


def stage_file(run, stage):
    """Path of a stage's file: <run>/<NN>-<stage>.json, NN the 1-based registry position."""
    for i, sid in enumerate(stage_ids(), start=1):
        if sid == stage:
            return Path(run) / f"{i:02d}-{stage}.json"
    raise ValueError(f"unknown stage: {stage!r}")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_stage(run, stage):
    """The stage's parsed JSON, or None when its file does not exist."""
    p = stage_file(run, stage)
    return _read_json(p) if p.is_file() else None


def write_stage(run, stage, data):
    """Write the stage file (UTF-8, sorted keys); returns its path."""
    p = stage_file(run, stage)
    _write_json(p, data)
    return p


def read_requirements(run):
    """Requirement items, [] when the file is absent."""
    p = Path(run) / REQUIREMENTS_FILE
    if not p.is_file():
        return []
    return list(_read_json(p).get("items", []))


def write_requirements(run, items):
    _write_json(Path(run) / REQUIREMENTS_FILE, {"items": list(items)})


def stage_claims(run, stage):
    """Claims list of a stage file ([] when absent)."""
    data = read_stage(run, stage)
    return list(data.get("claims", [])) if data else []


def has_source_link(claim):
    if not isinstance(claim, dict):
        return False
    link = claim.get("source_link")
    return isinstance(link, str) and bool(link.strip())


def evidenced_ids(run, stage):
    """Requirement ids named in `requirement_ids` by a claim with a non-empty
    source_link in the stage file. The one evidenced-definition the scorer and
    the sweep gate share."""
    ids = set()
    for claim in stage_claims(run, stage):
        if has_source_link(claim):
            ids.update(claim.get("requirement_ids") or [])
    return ids
