"""doctor-probe-select.py — manifest-driven probe selector for coordinator-doctor.

Purpose: read bin/doctor-probes.toml and emit probe ids matching the given
selection grammar. The sentinel (coordinator-doctor-sentinel.py) calls this
to resolve ACTIVE_PROBES for each run mode; tests call it directly to verify
selector invariants.

Spec backlink: archive/specs/2026-05-27-doctor-shape-doe-alignment.md § Chunk 4a.
Doctrine: docs/wiki/doctor-probe-design.md § Single-Entry-Point Consolidation
Must Stay Addressable.

CARGO-CULT GUARD: this selector operates on the fired-probe manifest only.
P-7a is EM-native and NOT in the manifest; --probe P-7a exits 2.

Exit codes:
  0 — selection succeeded; ids printed to stdout (one per line)
  2 — invalid selector argument (unknown cluster/probe/symptom, or no match)
  3 — tomllib unavailable (Python < 3.11 without tomllib backport)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def _manifest_path() -> Path:
    """Resolve the manifest path: env override or sibling to this script."""
    override = os.environ.get("DOCTOR_PROBES_MANIFEST")
    if override:
        return Path(override)
    return Path(__file__).parent / "doctor-probes.toml"


def load_probes() -> list[dict]:
    """Load and return the [[probe]] array from the manifest."""
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        print(
            "inconclusive: tomllib unavailable -- requires Python >= 3.11 "
            "(or install tomli backport). Cannot select probes.",
            file=sys.stderr,
        )
        sys.exit(3)

    manifest = _manifest_path()
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"inconclusive: manifest not found at {manifest}", file=sys.stderr)
        sys.exit(3)
    except Exception as exc:
        print(f"inconclusive: manifest parse error -- {exc}", file=sys.stderr)
        sys.exit(3)

    probes = data.get("probe", [])
    if not probes:
        print("inconclusive: manifest contains no [[probe]] entries", file=sys.stderr)
        sys.exit(3)
    return probes


# ---------------------------------------------------------------------------
# Selection modes
# ---------------------------------------------------------------------------

def select_triage(probes: list[dict]) -> list[str]:
    """Return ids where triage == true, in manifest order."""
    return [p["id"] for p in probes if p.get("triage") is True]


def select_full(probes: list[dict]) -> list[str]:
    """Return all ids in manifest order."""
    return [p["id"] for p in probes]


def select_cluster(probes: list[dict], name: str) -> list[str]:
    """Return ids in the named cluster. Unknown cluster exits 2 (fail-loud)."""
    known = sorted({p["cluster"] for p in probes})
    matched = [p["id"] for p in probes if p["cluster"] == name]
    if not matched:
        print(
            f"unknown cluster: {name} (known: {', '.join(known)})",
            file=sys.stderr,
        )
        sys.exit(2)
    return matched


def select_probe(probes: list[dict], probe_id: str) -> list[str]:
    """Return [id] if present in manifest; exits 2 if not (non-fired guard)."""
    matched = [p["id"] for p in probes if p["id"] == probe_id]
    if not matched:
        print(f"unknown probe: {probe_id}", file=sys.stderr)
        sys.exit(2)
    return matched


def select_symptom(probes: list[dict], text: str) -> list[str]:
    """Case-insensitive substring match against symptom_keywords.

    Returns ALL probe ids in any cluster that has a keyword match (cluster-expansion):
    matched clusters are collected first, then all probes in those clusters are returned.
    No match -> exit 2 (vacuous-GREEN guard -- never print empty set and exit 0).
    """
    needle = text.lower()
    matched_clusters: set[str] = set()
    for p in probes:
        for kw in p.get("symptom_keywords", []):
            if needle in kw.lower():
                matched_clusters.add(p["cluster"])
                break

    if not matched_clusters:
        print(f"no symptom match for: {text}", file=sys.stderr)
        sys.exit(2)

    # Emit all ids whose cluster is in matched_clusters, preserving manifest order.
    return [p["id"] for p in probes if p["cluster"] in matched_clusters]


def id_to_cluster(probes: list[dict], probe_id: str) -> str:
    """Return the cluster name for the given probe id; exits 2 if unknown."""
    for p in probes:
        if p["id"] == probe_id:
            return p["cluster"]
    print(f"unknown probe id: {probe_id}", file=sys.stderr)
    sys.exit(2)


def list_clusters(probes: list[dict]) -> list[str]:
    """Return sorted unique cluster names."""
    return sorted({p["cluster"] for p in probes})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    # Parse the single optional selector arg.
    # Supported: --triage, --full, --cluster NAME, --probe ID, --symptom TEXT,
    #            --list-clusters, --id-to-cluster ID
    # Default (no arg): --triage

    if len(argv) == 0:
        mode = "triage"
        mode_arg = None
    elif argv[0] == "--triage":
        if len(argv) != 1:
            print("--triage takes no arguments", file=sys.stderr)
            sys.exit(2)
        mode = "triage"
        mode_arg = None
    elif argv[0] == "--full":
        if len(argv) != 1:
            print("--full takes no arguments", file=sys.stderr)
            sys.exit(2)
        mode = "full"
        mode_arg = None
    elif argv[0] == "--cluster":
        if len(argv) != 2:
            print("--cluster requires exactly one NAME argument", file=sys.stderr)
            sys.exit(2)
        mode = "cluster"
        mode_arg = argv[1]
    elif argv[0] == "--probe":
        if len(argv) != 2:
            print("--probe requires exactly one ID argument", file=sys.stderr)
            sys.exit(2)
        mode = "probe"
        mode_arg = argv[1]
    elif argv[0] == "--symptom":
        if len(argv) < 2:
            print("--symptom requires a TEXT argument", file=sys.stderr)
            sys.exit(2)
        mode = "symptom"
        # Allow multi-word symptoms passed as separate args (join them).
        mode_arg = " ".join(argv[1:])
    elif argv[0] == "--list-clusters":
        if len(argv) != 1:
            print("--list-clusters takes no arguments", file=sys.stderr)
            sys.exit(2)
        mode = "list-clusters"
        mode_arg = None
    elif argv[0] == "--id-to-cluster":
        if len(argv) != 2:
            print("--id-to-cluster requires exactly one ID argument", file=sys.stderr)
            sys.exit(2)
        mode = "id-to-cluster"
        mode_arg = argv[1]
    else:
        print(
            f"unknown flag: {argv[0]} "
            "(valid: --triage, --full, --cluster NAME, --probe ID, "
            "--symptom TEXT, --list-clusters, --id-to-cluster ID)",
            file=sys.stderr,
        )
        sys.exit(2)

    probes = load_probes()

    if mode == "triage":
        ids = select_triage(probes)
    elif mode == "full":
        ids = select_full(probes)
    elif mode == "cluster":
        ids = select_cluster(probes, mode_arg)  # type: ignore[arg-type]
    elif mode == "probe":
        ids = select_probe(probes, mode_arg)  # type: ignore[arg-type]
    elif mode == "symptom":
        ids = select_symptom(probes, mode_arg)  # type: ignore[arg-type]
    elif mode == "list-clusters":
        for c in list_clusters(probes):
            print(c)
        return
    elif mode == "id-to-cluster":
        cluster = id_to_cluster(probes, mode_arg)  # type: ignore[arg-type]
        print(cluster)
        return
    else:
        # Should never reach here.
        sys.exit(2)

    for probe_id in ids:
        print(probe_id)


if __name__ == "__main__":
    main()
