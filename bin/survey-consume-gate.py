#!/usr/bin/env python3
"""coordinator/bin/survey-consume-gate.py — EM-side Phase-0.5 consume-gate,
in-process.

Purpose: hoists the whole Phase-0.5 consume-gate out of
`coordinator/pipelines/deep-architecture-survey/survey.workflow.js`'s
`agent()`-dispatched mechanical checks (the RAG-present predicate, the
`cartography.chunk_table`/`cartography.churn` op invocations, the windowed
readback of the chunk-table artifact, and the four consumer-side checks) into
one pure-stdlib Python script the EM runs directly, in-process, with no Haiku
agent dispatch on the hot path at all. Same consumer shape, same fail-toward-
absent defaults, same checks — a transport change, not a logic change.

Spec backlink: state/dispatch-briefs/2026-08-20-hoist-the-survey-consume-gate/C1.md;
docs/plans/2026-08-20-hoist-the-survey-consume-gate.md chunk C1.

Negative-spec: Phase 1's `invokeSymbolsExtraction`/`readSymbolsArtifactHeader`
are OUT of this script — their input is decided downstream of which branch
below ran, so a Phase-0 script cannot produce it. They stay on the agent lane
in `survey.workflow.js`.

I/O contract: reads one JSON object on stdin —
  {
    "repo_root": "<absolute path>",
    "claude_klabauter_root": "<absolute path to a claude-klabauter checkout>",
    "run_id": "<safe_id-shaped string>",
    "census_buckets": [{"bucketId": "...", "dirs": ["...", ...]}, ...],
    "mode": "first-run" | "refresh" | "targeted",
    "since": "<YYYY-MM-DD>" | null,
    "system_dirs": ["<dir>", ...] | null,
    "excluded_dirs": ["<dir>", ...] | null,
    "coverage_floor": <float> | null
  }
and writes ONE JSON object to stdout.

Coverage floor: `coverage_floor` overrides `DEFAULT_COVERAGE_FLOOR` (0.5) —
config is deliberately not a hardcoded constant, since a code repo
legitimately sits near 1.0 and a doctrine repo near 0.12. Report-only in
this chunk: the emitted `coverage.below_floor` is measured and logged every
run (thin or not), never turned into a decline here.

Exit contract: exits 0 in every case this script can classify — a declined
consumer-side check is reported via `{"ok": false, "declined_reason": "..."}`
in the emitted `chunk_table` field, never via a non-zero exit, so the caller
falls back to the agentic census wave on the PAYLOAD, not on an exit code. A
non-zero exit is reserved for this script's own internal crash (a bug in this
script), never a declined check, and never writes outside the run's own
scratch directory.

Windows-first: every `subprocess.run` call passes
`creationflags=CREATE_NO_WINDOW` (matching `test_cartography_chunk_table_
consume_gate_smoke.py`'s `_NO_CONSOLE`), an argument list (never
`shell=True`, never a heredoc), and every path goes through `pathlib`.

Percolation: `coordinator/bin/` in this repo does not percolate to the OSS
mirror (`source_map` resolves `bin`/`lib` against `claude-klabauter`), and
`coordinator/pipelines/` is not in the mirror allowlist either — the whole
cartography-dependent survey pipeline already reads as DoE-internal/
specialized. This script does not change that posture.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_NO_CONSOLE: dict[str, Any] = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

# The forward schema_version this consumer was written against — mirrors
# survey.workflow.js's CHUNK_TABLE_SCHEMA_VERSION. Bump only after reading
# the producer's newer shape and updating the mapping below to match.
CHUNK_TABLE_SCHEMA_VERSION = 2

# Line-count floor handed to the producer as `oversized_threshold`. The
# agentic census flags `loc > 800`; the producer flags `loc >= threshold`, so
# 801 makes both paths flag exactly the same file set instead of diverging on
# an exactly-800-line file.
CARTOGRAPHY_OVERSIZED_THRESHOLD = 801

# Conservative default for the Phase-0.5 coverage floor (fraction of a
# bucket's on-disk files the producer actually inventoried). A code repo
# legitimately sits near 1.0; a doctrine-heavy repo (this one) legitimately
# sits near 0.12 — no single constant serves both, so this default is
# deliberately biased toward flagging (never silently accepting a thin
# census) and `config["coverage_floor"]` is the caller's override, not a
# tuning knob buried in code. Report-only in this chunk (C1) — a ratio below
# this floor is measured and logged, never turned into a decline; C2 wires
# the decline.
DEFAULT_COVERAGE_FLOOR = 0.5


#: Last JSON-RPC error code seen per op key, populated by `_invoke_op`.
#: A side channel rather than a fourth return value, deliberately: `_invoke_op`
#: has two callers and only one of them needs the code, so widening the tuple
#: would churn a call site that has no use for it.
_LAST_OP_ERROR_CODE: dict[str, int] = {}

#: JSON-RPC code the engine returns for an op that was KILLED under the
#: process-time bar, as distinct from one that failed or declined. Measured,
#: not assumed — invoking the deleted `cartography.churn` returns exactly this
#: with "Killed, not suspended -- the old implementation does not come back."
_OP_KILLED_CODE = -32006

def _invoke_op(claude_klabauter_root: str, op: str, params: dict[str, Any]) -> tuple[int, dict[str, Any] | None, str | None]:
    """Runs `python3 -m coordinator_core.invoke <op> --params-file - --bare`
    against `claude_klabauter_root`, params over stdin, argument list only (never a
    shell string, never a heredoc).

    Returns `(exit_code, parsed_result_or_None, raw_stdout_or_stderr_on_
    failure)`. Per `cartographyOpBriefFor` (survey.workflow.js ~:361-372):
    exit 0 -> `--bare` stdout is the bare result object; exit 1 -> transient
    op-level error; exit 2 -> `error.code == STRUCTURAL_PIN_ERROR`,
    non-retryable. On non-zero exit `--bare` does not apply — stdout carries
    the full JSON-RPC envelope (or stderr, if stdout is empty).
    """
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "coordinator_core.invoke",
                op,
                "--params-file",
                "-",
                "--bare",
            ],
            input=json.dumps(params),
            cwd=claude_klabauter_root,
            capture_output=True,
            text=True,
            **_NO_CONSOLE,
        )
    except Exception as exc:
        return 1, None, f"subprocess invocation of {op} failed: {type(exc).__name__}: {exc}"

    if proc.returncode != 0:
        raw = proc.stdout or proc.stderr or ""
        return proc.returncode, None, raw

    try:
        result = json.loads(proc.stdout)
    except Exception as exc:
        return 0, None, f"{op} exit 0 but stdout was not valid JSON: {exc}: {proc.stdout!r}"

    # A top-level `error` key in a 0-exit result still means failure — this
    # literal check is load-bearing: `cartography.churn` genuinely returns
    # `{"error": str}` with exit 0.
    #
    # The JSON-RPC error CODE is carried out structurally rather than only
    # stringified into the message. `str(error_dict)` does technically contain
    # the code, but only a substring search over prose could recover it, and a
    # caller that must distinguish "declined on its merits" from "this op no
    # longer exists" cannot be asked to grep an error message to do it —
    # that is how the killed-op case spent weeks reading as a routine decline
    # (`state/bug-backlog/2026-09-01-cartography-churn-op-deleted-contract-
    # still-cites-it.yaml`).
    if isinstance(result, dict) and "error" in result:
        err = result.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            if isinstance(code, int):
                _LAST_OP_ERROR_CODE[op] = code
        return 0, None, str(err)

    return 0, result if isinstance(result, dict) else None, None


def _rag_predicate(repo_root: str) -> dict[str, Any]:
    """Single-authority RAG-present predicate — a disk check, no subprocess.

    Mirrors `phaseZeroFiveRagPredicate`'s failure branch: any error
    reports `rag_present: false`, never a silent skip of the gate.
    """
    try:
        root = Path(repo_root)
        manifest = root / ".project-rag" / "manifest.json"
        if not manifest.exists():
            return {
                "rag_present": False,
                "checked_path": str(manifest),
                "reason": "no .project-rag/manifest.json marker",
            }

        designated = "graph.db"
        try:
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(manifest_data, dict):
                candidate = manifest_data.get("structural_index_clang") or manifest_data.get(
                    "structural_index_lite"
                )
                if isinstance(candidate, str) and candidate:
                    designated = candidate
        except Exception:
            pass  # a malformed manifest falls back to the graph.db default

        artifact = root / ".project-rag" / designated
        if not artifact.exists():
            return {
                "rag_present": False,
                "checked_path": str(artifact),
                "reason": f"marker present but no {designated} (uninitialized)",
            }

        try:
            size = artifact.stat().st_size
        except OSError as exc:
            return {
                "rag_present": False,
                "checked_path": str(artifact),
                "reason": f"error reading {designated} size: {exc}",
            }

        if size == 0:
            return {
                "rag_present": False,
                "checked_path": str(artifact),
                "reason": f"{designated} present but zero bytes (empty index)",
            }

        return {
            "rag_present": True,
            "checked_path": str(artifact),
            "reason": "non-empty index found",
        }
    except Exception as exc:
        return {
            "rag_present": False,
            "checked_path": None,
            "reason": f"predicate check failed — defaulting to RAG-absent: {type(exc).__name__}: {exc}",
        }


def _read_chunk_table_artifact(repo_root: str, chunk_table_path: str) -> dict[str, Any] | None:
    """Resolves the artifact path as `Path(repo_root) / chunk_table_path`
    (rel-posix to `target_root`, per `cartography_chunk_table.py:341`),
    never opened directly, then `json.load()`. One call — replaces the
    header pass, the windowed reads, the per-window exactness check and the
    per-bucket reassembly cross-check the Workflow script's agentic transport
    needed, all at once (this script has a real filesystem primitive).
    """
    try:
        path = Path(repo_root) / chunk_table_path
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _run_cartography_extraction(config: dict[str, Any]) -> dict[str, Any]:
    """Ports `phaseZeroFiveCartographyExtraction` — the `cartography.
    chunk_table` invocation plus its four consumer-side checks. Returns a
    dict always carrying `ok`; `ok: false` carries `declined_reason`.
    """
    repo_root = config["repo_root"]
    claude_klabauter_root = config["claude_klabauter_root"]
    run_id = config["run_id"]
    census_buckets = config.get("census_buckets") or []

    if not census_buckets:
        return {
            "ok": False,
            "declined_reason": "no censusBuckets supplied — cartography.chunk_table requires "
            "caller-supplied system boundaries (absent/empty systems lands every file in "
            "unbucketed), declining the producer path",
        }

    systems = {bucket["bucketId"]: bucket["dirs"] for bucket in census_buckets}

    exit_code, emitted, error = _invoke_op(
        claude_klabauter_root,
        "cartography.chunk_table",
        {
            "target_root": repo_root,
            "run_id": run_id,
            "systems": systems,
            "chunk_size": 10,
            "emit": True,
            "oversized_threshold": CARTOGRAPHY_OVERSIZED_THRESHOLD,
        },
    )
    if exit_code != 0 or emitted is None:
        note = " [exitCode=2, STRUCTURAL_PIN_ERROR — non-retryable, contract pin is wedged]" if exit_code == 2 else f" [exitCode={exit_code}]"
        return {
            "ok": False,
            "declined_reason": f"cartography.chunk_table failed or unavailable ({error}){note} — "
            "falling back to the agentic census wave for this run",
        }

    chunk_table_path = emitted.get("chunk_table_path")
    if not chunk_table_path:
        return {
            "ok": False,
            "declined_reason": "cartography.chunk_table emitting reply carried no chunk_table_path "
            "— cannot read the artifact back, falling back to the agentic census wave",
        }

    read_back = _read_chunk_table_artifact(repo_root, chunk_table_path)
    if read_back is None:
        return {
            "ok": False,
            "declined_reason": f"could not read chunk-table artifact at {chunk_table_path} — "
            "falling back to the agentic census wave",
        }

    # Check 1: schema-version floor (accept <= 2). Fail loud on an unknown
    # FORWARD schema_version — mirrors claude-klabauter's own check_schema_version
    # contract.
    schema_version = read_back.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version > CHUNK_TABLE_SCHEMA_VERSION
    ):
        return {
            "ok": False,
            "declined_reason": f"cartography.chunk_table artifact schema_version={schema_version} "
            f"is newer than this consumer supports ({CHUNK_TABLE_SCHEMA_VERSION}) — falling back to "
            "the agentic census wave",
        }

    buckets = read_back.get("buckets") or {}

    # Check 2: truncation cross-check — sourced from the subprocess's STDOUT
    # reply's counts.bucketed_total, NEVER from the parsed artifact (the
    # artifact carries the same key, so sourcing it there would compare a
    # file to itself). Catches a producer-side or write-side truncation.
    read_back_total = sum(len((bucket or {}).get("files") or []) for bucket in buckets.values())
    reported_counts = emitted.get("counts") or {}
    reported_total = reported_counts.get("bucketed_total")
    if not isinstance(reported_total, (int, float)) or isinstance(reported_total, bool) or read_back_total != reported_total:
        return {
            "ok": False,
            "declined_reason": f"cartography.chunk_table truncation cross-check failed — read-back "
            f"sums to {read_back_total} files, emitting reply reported counts.bucketed_total="
            f"{reported_total} — falling back to the agentic census wave",
        }

    # Check 3: bucket identity — exact match against supplied CENSUS_BUCKETS.
    supplied_bucket_ids = sorted(bucket["bucketId"] for bucket in census_buckets)
    returned_bucket_ids = sorted(buckets.keys())
    if supplied_bucket_ids != returned_bucket_ids:
        return {
            "ok": False,
            "declined_reason": f"cartography.chunk_table returned bucket set "
            f"[{', '.join(returned_bucket_ids)}] does not match supplied CENSUS_BUCKETS "
            f"[{', '.join(supplied_bucket_ids)}] — falling back to the agentic census wave",
        }

    # Check 4: per-bucket prefix containment. Deliberately loose startsWith —
    # carried as-is, not tightened (see brief: a stricter match could newly
    # reject a file that passes today, a behaviour change with no test
    # coverage here).
    supplied_dirs_by_bucket_id = {bucket["bucketId"]: bucket["dirs"] for bucket in census_buckets}
    for system_name, bucket in buckets.items():
        prefixes = supplied_dirs_by_bucket_id.get(system_name, [])
        files = (bucket or {}).get("files") or []
        offender = next((path for path in files if not any(path.startswith(prefix) for prefix in prefixes)), None)
        if offender is not None:
            return {
                "ok": False,
                "declined_reason": f'cartography.chunk_table bucket "{system_name}" contains file '
                f'"{offender}" outside its supplied dirs prefixes [{", ".join(prefixes)}] — falling '
                "back to the agentic census wave",
            }

    # Map buckets into the census-shaped result Phase 1/2/3 already consume.
    oversized_raw = emitted.get("oversized")
    oversized_paths = set(oversized_raw) if isinstance(oversized_raw, list) else None
    census_shaped_results = [
        {
            "bucket_id": system_name,
            "files": [
                {
                    "path": path,
                    "loc": None,
                    "oversized": oversized_paths is not None and path in oversized_paths,
                }
                for path in ((bucket or {}).get("files") or [])
            ],
            "anomalies": [],
        }
        for system_name, bucket in buckets.items()
    ]

    unbucketed_count = (read_back.get("counts") or {}).get("unbucketed_total") or 0

    return {
        "ok": True,
        "censusShapedResults": census_shaped_results,
        "chunkTablePath": chunk_table_path,
        "counts": read_back.get("counts") or emitted.get("counts"),
        "oversizedSignalAvailable": oversized_paths is not None,
        "oversizedCount": len(oversized_paths) if oversized_paths else 0,
        "unbucketedCount": unbucketed_count,
    }


def _count_files_on_disk(repo_root: str, dirs: list[str]) -> int:
    """Counts every file actually present under each of `dirs` (relative to
    `repo_root`), recursively. A missing/non-directory entry contributes 0,
    never raises — this is a measurement, not a check that can decline.
    """
    total = 0
    root = Path(repo_root)
    for rel_dir in dirs:
        candidate = root / rel_dir
        if not candidate.is_dir():
            continue
        try:
            total += sum(1 for p in candidate.rglob("*") if p.is_file())
        except OSError:
            continue
    return total


def _measure_bucket_coverage(
    repo_root: str,
    census_buckets: list[dict[str, Any]],
    census_shaped_results: list[dict[str, Any]],
    floor: float,
) -> dict[str, Any]:
    """The fifth consumer-side measurement: for each census bucket, compares
    the inventoried file count (what the producer actually returned) against
    the count of files present on disk under that bucket's declared `dirs`.

    Report-only (see `DEFAULT_COVERAGE_FLOOR`): computes and logs the ratio,
    every run, thin or not — never turns a low ratio into `ok: false`. The
    caller decides what to do with `below_floor`; this function only measures.
    """
    inventoried_by_bucket = {
        entry.get("bucket_id"): len(entry.get("files") or []) for entry in census_shaped_results
    }

    buckets: dict[str, Any] = {}
    total_inventoried = 0
    total_on_disk = 0
    for bucket in census_buckets:
        bucket_id = bucket["bucketId"]
        dirs = bucket.get("dirs") or []
        inventoried = inventoried_by_bucket.get(bucket_id, 0)
        on_disk = _count_files_on_disk(repo_root, dirs)
        ratio = (inventoried / on_disk) if on_disk else None
        buckets[bucket_id] = {
            "inventoried": inventoried,
            "on_disk": on_disk,
            "ratio": ratio,
        }
        total_inventoried += inventoried
        total_on_disk += on_disk

    overall_ratio = (total_inventoried / total_on_disk) if total_on_disk else None
    below_floor = overall_ratio is not None and overall_ratio < floor

    result = {
        "floor": floor,
        "buckets": buckets,
        "total_inventoried": total_inventoried,
        "total_on_disk": total_on_disk,
        "overall_ratio": overall_ratio,
        "below_floor": below_floor,
    }

    print(
        f"survey-consume-gate: coverage {total_inventoried}/{total_on_disk} "
        f"(ratio={overall_ratio}, floor={floor}, below_floor={below_floor})",
        file=sys.stderr,
    )

    return result


def _run_churn(config: dict[str, Any]) -> dict[str, Any] | None:
    """Ports `phaseZeroFiveChurn`. `cartography.churn` runs ONLY in refresh
    mode. When not in refresh mode, or when refresh mode is missing `since`/
    `system_dirs`, reproduces the discriminated skip shape —
    `{"skipped": true, "reason": "missing-since-or-systemDirs"}` — rather
    than erroring or omitting the key.
    """
    mode = config.get("mode") or "first-run"
    if mode != "refresh":
        return None

    since = config.get("since")
    system_dirs = config.get("system_dirs")
    if not since or not system_dirs:
        return {"skipped": True, "reason": "missing-since-or-systemDirs"}

    params: dict[str, Any] = {
        "target_root": config["repo_root"],
        "since": since,
        "system_dirs": system_dirs,
    }
    excluded_dirs = config.get("excluded_dirs")
    if excluded_dirs:
        params["excluded_dirs"] = excluded_dirs

    exit_code, result, error = _invoke_op(config["claude_klabauter_root"], "cartography.churn", params)
    if exit_code != 0 or result is None:
        # A KILLED op is not a decline, and must not be reported as one.
        # `architecture-survey.md` tells the reader a decline in a fallback log
        # is "a designed path, not a break". That sentence was written for a
        # gate that could decline ON ITS MERITS. An op the engine has killed
        # cannot decline on anything: every refresh takes the agentic fallback
        # at higher cost and reports itself working, which is what hid this for
        # weeks. Same answer for two different states, one of them this
        # instrument's own failure to look.
        if _LAST_OP_ERROR_CODE.get("cartography.churn") == _OP_KILLED_CODE:
            return {
                "ok": False,
                "producer_missing": True,
                "declined_reason": f"BREAK, not a decline: cartography.churn has been KILLED in "
                f"the engine and has no producer ({error}) — the agentic census wave is running "
                "in its place at higher cost on EVERY refresh, and will keep doing so silently "
                "until a replacement producer is built. This is not the designed fallback path.",
            }
        note = " [exitCode=2, STRUCTURAL_PIN_ERROR — non-retryable, contract pin is wedged]" if exit_code == 2 else f" [exitCode={exit_code}]"
        return {
            "ok": False,
            "declined_reason": f"cartography.churn failed or unavailable ({error}){note} — falling "
            "back to the agentic census wave for this run",
        }
    return result


def run_gate(config: dict[str, Any]) -> dict[str, Any]:
    """Runs the whole Phase-0.5 gate against `config`, in-process, and
    returns the manifest object this script writes to stdout.
    """
    rag = _rag_predicate(config["repo_root"])

    chunk_table: dict[str, Any] | None = None
    if not rag.get("rag_present"):
        chunk_table = _run_cartography_extraction(config)

    churn_result = _run_churn(config)

    coverage: dict[str, Any] | None = None
    if chunk_table is not None and chunk_table.get("ok"):
        raw_floor = config.get("coverage_floor")
        floor = raw_floor if isinstance(raw_floor, (int, float)) and not isinstance(raw_floor, bool) else DEFAULT_COVERAGE_FLOOR
        coverage = _measure_bucket_coverage(
            config["repo_root"],
            config.get("census_buckets") or [],
            chunk_table.get("censusShapedResults") or [],
            floor,
        )

    return {
        "rag_present": rag.get("rag_present"),
        "rag_predicate": rag,
        "chunk_table": chunk_table,
        "churn_result": churn_result,
        "coverage": coverage,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        raw = sys.stdin.read()
    except Exception as exc:
        json.dump({"error": f"failed to read stdin: {type(exc).__name__}: {exc}"}, sys.stdout)
        return 1

    try:
        config = json.loads(raw)
        if not isinstance(config, dict):
            raise ValueError("config must be a JSON object")
    except Exception as exc:
        json.dump({"error": f"failed to parse stdin config JSON: {type(exc).__name__}: {exc}"}, sys.stdout)
        return 1

    try:
        manifest = run_gate(config)
    except Exception as exc:
        json.dump({"error": f"internal crash: {type(exc).__name__}: {exc}"}, sys.stdout)
        return 1

    json.dump(manifest, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
