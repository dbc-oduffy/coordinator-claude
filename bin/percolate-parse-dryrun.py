# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""percolate-parse-dryrun.py — naked-Python assembler computing the
`/percolate` skill's (DoE-claude coordinator/skills/percolate/SKILL.md)
dry-run-stdout parse steps and the Step-3 PM-confirmation gate-fire
predicate as a single decision-object envelope.

Ports the reader-performed stdout-parsing narration at Step 2 (L102-106:
deletions / total-touched-file-count / sensitive-path detection), Step 2b
(L133-137: impact-radius top-directories / file-types / sensitive-paths
summary), Step 2c's scan-file-list build (L147 -- this chunk supersedes
that line's "This is a mechanical text transform — do it directly ...
rather than shelling out" instruction; the parse now lives here instead
of being narrated as reader work), and the Step-3 gate-fire predicate
(L214-219: deletion present OR >=10 files touched OR a sensitive path
touched OR Step 2c reported >=1 MEDIUM content-leak hit OR Step 2d
reported >=1 real inverse-drift commit).

Subcommand:
  parse-dryrun --stdout-file <path> --source-dir <path>
               [--medium-leak-count N] [--inverse-drift-count N]
      Reads the captured `publish --dry-run <target>` stdout from
      <stdout-file>, computes every field above, and prints the 8-key
      decision-object envelope (build_envelope/emit) as JSON. The Step-3
      gate, when it fires, is represented as one
      `build_untrusted_gate_judgment_point` entry in `judgment_points[]`
      (never `build_judgment_point` -- the firing condition is derived
      from dry-run stdout, i.e. content this engine does not fully trust
      to judge its own significance; per the Staff Engineer F3, an untrusted-gate
      judgment point structurally carries no `recommendation`). Exits 0
      on a successful compute; the gate's fire/no-fire outcome is a field
      in the envelope, not the process exit code -- the skill (the
      trusted caller) reads `judgment_points[]` to decide whether to
      pause for PM confirmation.

Negative-spec: this module does NOT invoke `publish.py`, does NOT run the
Step 2c/2d scans itself (`percolate-gate scan-secrets` / `inverse-drift`
own those; their hit counts are passed in as `--medium-leak-count` /
`--inverse-drift-count`), and does NOT re-derive
`build_envelope`/`emit`/`build_judgment_point`/`build_untrusted_gate_judgment_point`
-- imported from the shipped canonical library
(`coordinator_core.contract.decision_object`), never copied per the
pickup_assemble CONSUME-DON'T-RE-DERIVE hazard.

Spec backlink: coordinator/skills/percolate/SKILL.md (DoE-claude) — Step 2,
Step 2b, Step 2c, Step 3. Port chunk: b8-C5.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, List, Optional

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BIN_DIR.parent.parent

_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    """Put the repo root on sys.path so `coordinator_core` imports resolve.

    Moved out of module scope: this used to mutate sys.path on every import
    of this file, a process global ~50 warm-server sessions share. Only the
    trigger moved.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    _BOOTSTRAP_DONE = True


#: Step 3's sensitive-path predicate (L214-219 / Step 2's L102-106) — same
#: four categories in both places, kept as one constant so the two checks
#: can't drift apart.
_SENSITIVE_MARKERS = ("CLAUDE.md", "settings.json", "hooks/", "agents/")

#: Step 3's file-count threshold.
_GATE_FILE_COUNT_THRESHOLD = 10

_UPDATE_OR_NEW = re.compile(r"^(?:UPDATE|NEW): (?P<path>.+)$")
_DELETING = re.compile(r"\b(deleting|del\.)\b")


def _touched_paths(stdout_text: str) -> List[str]:
    """Every `UPDATE: <path>` / `NEW: <path>` rel-path from rsync's
    dry-run stdout, in stdout order (Step 2c's file-set build)."""
    paths: List[str] = []
    for line in stdout_text.splitlines():
        match = _UPDATE_OR_NEW.match(line.strip())
        if match:
            paths.append(match.group("path"))
    return paths


def _has_deletions(stdout_text: str) -> bool:
    return any(_DELETING.search(line) for line in stdout_text.splitlines())


def _sensitive_hits(paths: List[str]) -> List[str]:
    hits: List[str] = []
    for path in paths:
        for marker in _SENSITIVE_MARKERS:
            if marker.endswith("/"):
                matched = path.startswith(marker) or f"/{marker}" in path
            else:
                matched = path == marker or path.endswith(f"/{marker}")
            if matched and marker not in hits:
                hits.append(marker)
    return hits


def _ignore_missing(stdout_text: str) -> bool:
    return "No .percolate-ignore found at" in stdout_text


def _top_dirs(paths: List[str], limit: int = 5) -> List[List[Any]]:
    """Step 2b's top-5-by-file-count directory summary, at
    `<top-level>/<second-level>` granularity."""
    counts: dict[str, int] = {}
    for path in paths:
        parts = Path(path).parts
        key = "/".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else path)
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [[name, count] for name, count in ranked[:limit]]


def _file_types(paths: List[str]) -> dict[str, int]:
    """Step 2b's extension breakdown: md / sh / py / other."""
    counts = {"md": 0, "sh": 0, "py": 0, "other": 0}
    for path in paths:
        suffix = Path(path).suffix.lstrip(".").lower()
        if suffix in ("md", "sh", "py"):
            counts[suffix] += 1
        else:
            counts["other"] += 1
    return counts


def _scan_file_list(source_dir: Path, paths: List[str]) -> List[str]:
    """Step 2c's absolute-path scan-file-list build (supersedes the
    surviving L147 "do it directly" reader-performed-transform prose)."""
    return [str(source_dir / rel_path) for rel_path in paths]


def compute_gate_fire(
    *,
    has_deletions: bool,
    file_count: int,
    sensitive_hits: List[str],
    medium_leak_count: int,
    inverse_drift_count: int,
) -> bool:
    """Step 3's gate-fire predicate (L214-219): fires iff any of —
    a deletion is present, >=10 files touched, a sensitive path touched,
    >=1 MEDIUM content-leak hit, or >=1 real inverse-drift commit."""
    return (
        has_deletions
        or file_count >= _GATE_FILE_COUNT_THRESHOLD
        or bool(sensitive_hits)
        or medium_leak_count >= 1
        or inverse_drift_count >= 1
    )


def _gate_judgment_point(
    *,
    has_deletions: bool,
    file_count: int,
    sensitive_hits: List[str],
    medium_leak_count: int,
    inverse_drift_count: int,
) -> dict[str, Any]:
    reasons: List[str] = []
    if has_deletions:
        reasons.append("deletion present")
    if file_count >= _GATE_FILE_COUNT_THRESHOLD:
        reasons.append(f"{file_count} files touched (>= {_GATE_FILE_COUNT_THRESHOLD})")
    if sensitive_hits:
        reasons.append(f"sensitive path(s) touched: {', '.join(sensitive_hits)}")
    if medium_leak_count >= 1:
        reasons.append(f"{medium_leak_count} MEDIUM content-leak hit(s)")
    if inverse_drift_count >= 1:
        reasons.append(f"{inverse_drift_count} real inverse-drift commit(s)")
    _bootstrap_engine()
    from coordinator_core.contract.decision_object.judgment import (
        build_disposition,
        build_untrusted_gate_judgment_point,
    )

    evidence = "; ".join(reasons) if reasons else "no gate-fire condition met"
    return build_untrusted_gate_judgment_point(
        id="jp_step3_percolate_confirmation_gate",
        question="Step 3 PM-confirmation gate: proceed with this publish?",
        dispositions=[
            build_disposition("confirm", resolves=["d_step4_real_run"]),
            build_disposition("abort"),
        ],
        evidence=evidence,
        reason="untrusted-dryrun-derived-significance",
        revalidate_at_dispatch=True,
        round_trip="terminal",
    )


def _cmd_parse_dryrun(args: argparse.Namespace) -> int:
    _bootstrap_engine()
    from coordinator_core.contract.decision_object.envelope import (
        build_envelope,
        emit,
        extend_exit_codes,
    )

    PercolateParseExitCode = extend_exit_codes(
        "PercolateParseExitCode",
        USAGE=2,
        TRANSPORT_FAIL=3,
    )

    stdout_path = Path(args.stdout_file)
    source_dir = Path(args.source_dir)
    try:
        stdout_text = stdout_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        print(f"percolate-parse-dryrun: cannot read {stdout_path}: {exc}", file=sys.stderr)
        return int(PercolateParseExitCode.TRANSPORT_FAIL)

    paths = _touched_paths(stdout_text)
    has_deletions = _has_deletions(stdout_text)
    sensitive = _sensitive_hits(paths)
    ignore_missing = _ignore_missing(stdout_text)

    preflight: dict[str, Any] = {
        "step2_has_deletions": has_deletions,
        "step2_file_count": len(paths),
        "step2_sensitive_paths": sensitive,
        "step2_percolate_ignore_missing": ignore_missing,
        "step2b_impact_radius": {
            "top_directories": _top_dirs(paths),
            "file_types": _file_types(paths),
            "sensitive_paths": sensitive,
        },
        "step2c_scan_file_list": _scan_file_list(source_dir, paths),
    }

    gate_fires = compute_gate_fire(
        has_deletions=has_deletions,
        file_count=len(paths),
        sensitive_hits=sensitive,
        medium_leak_count=args.medium_leak_count,
        inverse_drift_count=args.inverse_drift_count,
    )

    judgment_points: List[dict[str, Any]] = []
    if gate_fires:
        judgment_points.append(
            _gate_judgment_point(
                has_deletions=has_deletions,
                file_count=len(paths),
                sensitive_hits=sensitive,
                medium_leak_count=args.medium_leak_count,
                inverse_drift_count=args.inverse_drift_count,
            )
        )

    envelope = build_envelope(
        artifact={"kind": "skill-step", "name": "percolate-parse-dryrun"},
        preflight=preflight,
        gates={"step3_gate_fires": gate_fires},
        directives=[],
        judgment_points=judgment_points,
        decisions={},
        narration=(
            "Step 2/2b/2c dry-run-stdout parse computed; Step 3 gate-fire "
            f"predicate resolved to {gate_fires}."
        ),
        next_move=(
            "PM-confirm the jp_step3_percolate_confirmation_gate judgment point"
            if gate_fires
            else "proceed directly (no gate-fire condition met)"
        ),
    )
    emit(envelope)
    print(json.dumps(envelope, indent=2, sort_keys=True))
    return int(PercolateParseExitCode.SUCCESS)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="percolate-parse-dryrun")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_parse = sub.add_parser("parse-dryrun")
    p_parse.add_argument("--stdout-file", required=True)
    p_parse.add_argument("--source-dir", required=True)
    p_parse.add_argument("--medium-leak-count", type=int, default=0)
    p_parse.add_argument("--inverse-drift-count", type=int, default=0)
    p_parse.set_defaults(func=_cmd_parse_dryrun)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
