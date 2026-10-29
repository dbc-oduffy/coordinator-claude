"""EM-side symbols step for the deep architecture survey.

Preflights ``symbol_extract``, runs ``cartography.symbols`` over the survey's deduped file list,
reads the artifact whole, and writes a receipt (``symbols-receipt.schema.json``) under
``state/scratch/deep-architecture-survey/<run-id>/``. Exit codes: 0 ok, 2 usage/input error,
3 symbol_extract missing, 4 artifact pre-exists, 5 any other halt (receipt carries the label).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import subprocess
import sys
from pathlib import Path

INSTALL_LINE = 'python3 -m pip install ".[tree-sitter]"'
SUBCHUNK_SIZE = 10
EXIT_CODES = {
    "symbol-extract-missing": 3,
    "symbols-artifact-preexists": 4,
}
OTHER_HALT_EXIT = 5


def _no_console() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def scratch_dir(repo_root: Path, run_id: str) -> Path:
    return repo_root / "state" / "scratch" / "deep-architecture-survey" / run_id


def _env(engine_root: Path) -> dict:
    env = dict(os.environ)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(engine_root) + (os.pathsep + prior if prior else "")
    return env


def _blank_receipt(artifact: Path, chunk_table: Path, requested: int = 0) -> dict:
    return {
        "ok": False,
        "halt": None,
        "artifact_path": str(artifact),
        "chunk_table_path": str(chunk_table),
        "total_files": 0,
        "requested_files": requested,
        "unavailable_count": 0,
        "unsupported_count": 0,
        "unavailable_sample": [],
        "unsupported_extensions": [],
        "coverage_note": None,
    }


def preflight(engine_root: Path) -> subprocess.CompletedProcess:
    """Probe the interpreter and PYTHONPATH the cartography invoke will import from."""
    return subprocess.run(
        [sys.executable, "-c", "import symbol_extract"],
        env=_env(engine_root),
        capture_output=True,
        text=True,
        creationflags=_no_console(),
    )


def _buckets_from_gate(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    table = data.get("chunk_table", data) if isinstance(data, dict) else data
    if isinstance(table, dict):
        table = table.get("censusShapedResults")
    if not isinstance(table, list):
        raise ValueError(f"{path}: no chunk_table.censusShapedResults list")
    return table


def _buckets_from_census_dir(census_dir: Path) -> list:
    buckets = []
    for p in sorted(census_dir.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "files" in data:
            data.setdefault("bucket_id", p.stem)
            buckets.append(data)
    if not buckets:
        raise ValueError(f"{census_dir}: no per-bucket census JSON found")
    return buckets


def build_chunk_table(buckets: list) -> list:
    """Sub-chunks of SUBCHUNK_SIZE files per bucket, mirroring the workflow's chunk shape."""
    chunks = []
    for bucket in buckets:
        files = [f["path"] if isinstance(f, dict) else f for f in bucket.get("files", [])]
        oversized = {
            f["path"] for f in bucket.get("files", []) if isinstance(f, dict) and f.get("oversized")
        }
        if not files:
            continue
        count = -(-len(files) // SUBCHUNK_SIZE)
        for i in range(count):
            piece = files[i * SUBCHUNK_SIZE:(i + 1) * SUBCHUNK_SIZE]
            chunks.append({
                "systemName": bucket.get("bucket_id") or bucket.get("systemName"),
                "subChunkLabel": chr(65 + i) if count > 1 else "—",
                "files": piece,
                "oversizedFiles": [p for p in piece if p in oversized],
            })
    return chunks


def dedupe_files(chunk_table: list) -> list:
    seen, out = set(), []
    for chunk in chunk_table:
        for f in chunk["files"]:
            if f not in seen:
                seen.add(f)
                out.append(f)
    return out


def summarize_artifact(artifact: Path) -> dict:
    data = json.loads(artifact.read_text(encoding="utf-8"))
    files = data.get("files") or []
    unavailable = [f for f in files if f.get("unavailable") is True]
    unsupported = [f for f in files if f.get("unsupported") is True]
    ext = collections.Counter(os.path.splitext(f.get("path") or "")[1].lower() for f in unsupported)
    return {
        "total_files": len(files),
        "unavailable_count": len(unavailable),
        "unsupported_count": len(unsupported),
        "unavailable_sample": [
            {"path": f.get("path") or "", "reason": f.get("detail") or ""} for f in unavailable[:50]
        ],
        "unsupported_extensions": [
            {"ext": e or "(none)", "count": n} for e, n in ext.most_common()
        ],
        "coverage_note": data.get("coverage_note") or None,
    }


def run_step(args: argparse.Namespace) -> tuple[int, dict, str]:
    """Returns (exit_code, receipt, stderr_text). Writes the receipt file."""
    repo_root = Path(args.repo_root)
    engine_root = Path(args.engine_root)
    sdir = scratch_dir(repo_root, args.run_id)
    artifact = sdir / f"cartography-symbols-{args.run_id}.json"
    params = sdir / f"cartography-symbols-params-{args.run_id}.json"
    chunk_path = sdir / "chunk-table.json"
    receipt_path = sdir / "symbols-receipt.json"
    receipt = _blank_receipt(artifact, chunk_path)
    stderr = ""

    def finish(halt: str | None, code: int) -> tuple[int, dict, str]:
        receipt["halt"] = halt
        receipt["ok"] = halt is None
        sdir.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return code, receipt, stderr

    probe = preflight(engine_root)
    if probe.returncode != 0:
        stderr = (
            "symbol_extract is not importable; install it from the symbol-extract package:\n"
            f"  {INSTALL_LINE}\n{probe.stderr}"
        )
        return finish("symbol-extract-missing", EXIT_CODES["symbol-extract-missing"])
    if args.preflight_only:
        return 0, receipt, ""

    if artifact.exists():
        stderr = (f"pre-existing symbols artifact, not deleted or read: {artifact}\n"
                  "a failed earlier attempt of this run leaves one: remove it, or use a new --run-id, then re-run\n")
        return finish("symbols-artifact-preexists", EXIT_CODES["symbols-artifact-preexists"])

    try:
        if args.consume_gate_output:
            buckets = _buckets_from_gate(Path(args.consume_gate_output))
        else:
            buckets = _buckets_from_census_dir(Path(args.census_dir))
    except (OSError, ValueError) as exc:
        return 2, receipt, f"chunk table input error: {exc}\n"

    chunk_table = build_chunk_table(buckets)
    files = dedupe_files(chunk_table)
    receipt["requested_files"] = len(files)
    sdir.mkdir(parents=True, exist_ok=True)
    chunk_path.write_text(json.dumps(chunk_table, indent=2), encoding="utf-8")
    if not files:
        return 2, receipt, "empty chunk table: no files to extract symbols for\n"
    params.write_text(json.dumps({"target_root": str(repo_root), "files": files}), encoding="utf-8")

    with artifact.open("wb") as out:
        proc = subprocess.run(
            [sys.executable, "-m", "coordinator_core.invoke", "cartography.symbols",
             "--params-file", str(params), "--bare"],
            env=_env(engine_root),
            stdout=out,
            stderr=subprocess.PIPE,
            creationflags=_no_console(),
        )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", "replace")
        return finish("symbols-producer-failed", OTHER_HALT_EXIT)

    try:
        receipt.update(summarize_artifact(artifact))
    except (OSError, ValueError) as exc:
        stderr = f"artifact unreadable: {exc}\n"
        return finish("symbols-producer-failed", OTHER_HALT_EXIT)

    if receipt["total_files"] != len(files):
        stderr = (f"artifact carries {receipt['total_files']} file entries, "
                  f"requested {len(files)}: truncation fault\n")
        return finish("symbols-coverage-truncated", OTHER_HALT_EXIT)
    if receipt["unavailable_count"] > 0:
        stderr = (f"{receipt['unavailable_count']} file(s) unattemptable: extractor unavailable; "
                  f"install: {INSTALL_LINE}\n")
        return finish("symbols-extractor-unavailable", OTHER_HALT_EXIT)
    return finish(None, 0)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--engine-root", required=True)
    ap.add_argument("--run-id", required=True)
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--consume-gate-output")
    src.add_argument("--census-dir")
    ap.add_argument("--preflight-only", action="store_true")
    args = ap.parse_args(argv)
    if not args.preflight_only and not (args.consume_gate_output or args.census_dir):
        ap.error("one of --consume-gate-output or --census-dir is required")
    code, receipt, err = run_step(args)
    if err:
        sys.stderr.write(err)
    if not args.preflight_only or code != 0:
        print(scratch_dir(Path(args.repo_root), args.run_id) / "symbols-receipt.json")
    return code


if __name__ == "__main__":
    sys.exit(main())
