# Unix shebang.
"""classify-env-var-callers.py — mechanical bucket enumerator for the engine-root
ENV VAR retirement (C20, docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md).

Sibling of `classify-resolver-callers.py`, which buckets callers of the resolver
SYMBOL family. This script buckets callers of the engine-root ENV VAR — the
surface C11 must route and C18 must split by axis. The two scripts overlap in
files and answer different questions; neither replaces the other.

WHY A SCRIPT AND NOT A GREP. A raw grep for the variable returns hundreds of hits
across hundreds of files. C11's question is per-site three-way — (a) reads the
engine root, (b) exports it to children, (c) genuinely wants the claude-klabauter SOURCE
CHECKOUT — and a blanket answer is the exact defect the workstream exists to fix:
routing a (c) site to the engine accessor silently repoints it, and nothing fails
loudly when it happens.

THE (a)/(b) SPLIT IS MECHANICALLY DECIDABLE, and C20's body says so: a site that
puts the name into a dict or environment handed to a child is a WRITER; everything
else reads.

THE (a)/(c) SPLIT IS ALSO LARGELY MECHANICAL, which C20's body did NOT anticipate
and which is this script's substantive addition. A dispatch-axis caller uses the
resolved root for exactly one thing: putting `coordinator_core` on `sys.path`, or
handing the root to `cc_invoke`/an install step that consumes the engine. A
locator-axis caller instead treats it as a filesystem anchor for REPO CONTENT —
joining it to a source path, globbing under it, comparing checked-in bytes. That
distinction is visible in the AST at every use site of the bound name, so the
residual needing human review is a handful rather than the whole set.

NEGATIVE SPEC — this script MEASURES, it does not assert. Numbers drift as the
tree changes; the plan prose that quoted an earlier run is allowed to go stale,
and a re-run disagreeing with a prose figure is the signal, not a bug here. Do not
hardcode expectations from a doc into this file. In particular the emitted FILE
LISTS are derive-at-execution-time inputs for a wave brief, never a frozen roster:
run it, read what it prints.

Usage:
    python classify-env-var-callers.py [--root PATH] [--out PATH] [--json]

Exit code: always 0 (an enumeration tool, not a gate).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_DEFAULT = _SCRIPT_DIR.parent.parent

_EXCLUDE_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".venv", "venv",
}

# Historical-record trees. C13's exclusion filter under-covered its own stated
# rationale by using a prefix list; the rationale is "records of what was true
# when written", and decision records plus delivered plans are exactly that.
# Enumerating them here would put immutable history into a routing wave.
_EXCLUDE_PREFIXES = (
    "state/", "archive/", "cross-repo/", "tasks/", "docs/decisions/",
)

_VAR_NAMES = ("CLAUDE_KLABAUTER_ROOT", "COORDINATOR_ENGINE_ROOT", "COORDINATOR_ENGINE_SOURCE_ROOT")
_VAR_ALT = "|".join(_VAR_NAMES)

# A site that puts the variable into a mapping handed onward is a WRITER.
_WRITER_PATTERNS = [
    re.compile(rf"""\[\s*["'](?:{_VAR_ALT})["']\s*\]\s*="""),
    re.compile(rf"""environ\.setdefault\(\s*["'](?:{_VAR_ALT})["']"""),
    re.compile(rf"""["'](?:{_VAR_ALT})["']\s*:"""),          # dict literal member
    re.compile(rf"""putenv\(\s*["'](?:{_VAR_ALT})["']"""),
]

# Reads of the variable, and the resolver family that wraps those reads.
_READ_PATTERNS = [
    re.compile(rf"""environ(?:\.get)?\(?\s*\[?\s*["'](?:{_VAR_ALT})["']"""),
    re.compile(rf"""getenv\(\s*["'](?:{_VAR_ALT})["']"""),
]

# Both spellings of a dispatch-axis resolve. `require_dispatch_engine_on_path`
# is C16's seam and wraps `_resolve_claude_klabauter_root`; a file that adopted the seam is
# the SAME call site it was before the collapse, so it must stay in the census.
# Counting only the bare symbol would have made ~190 sites vanish from the table
# the moment C16 landed, which reads as "already routed" and is not.
_RESOLVER_CALL = re.compile(r"\b(?:_resolve_claude_klabauter_root|require_dispatch_engine_on_path)\s*\(")
_RESOLVER_BINDERS = {"_resolve_claude_klabauter_root", "require_dispatch_engine_on_path"}
_SEAM_CALL = re.compile(r"\brequire_dispatch_engine_on_path\s*\(")

# Use sites that consume the ENGINE (dispatch axis).
_DISPATCH_USE = re.compile(
    r"sys\.path|cc_invoke\(|pip[\"']?,\s*[\"']install|run_op_main|import_module|"
    r"coordinator_core"
)

_SCAN_EXTENSIONS = {".py"}

# Reviewed dispositions for the one bucket that needs human judgement.
#
# WHY THIS LIVES IN THE SCRIPT AND NOT IN THE GENERATED TABLE. The table is
# regenerated on every run and carries a do-not-hand-edit banner; a verdict
# written there is erased by the next run, which is how a reviewed set silently
# becomes an unreviewed one. Keyed by repo-relative path so a file that MOVES
# falls out of the map and re-enters the review bucket rather than inheriting a
# verdict that was reached about a different location.
#
# `dispatch` — the resolved root is consumed as THE ENGINE: put on a child's
#   PYTHONPATH, handed to `cc_invoke`, pip-installed, or checked for
#   `coordinator_core`. These are heuristic false positives: the use site is
#   dispatch-shaped but did not match the line-level pattern.
# `locator`  — the resolved root is a filesystem anchor for REPO CONTENT. These
#   are C11's genuine case (c) and must NOT move to the engine accessor.
# `ladder`   — the resolution machinery itself, not a consumer of it.
# `fixture`  — a test asserting ON the resolver, with synthetic roots. C12's
#   surface (the name as data), never C11's (the name as a read).
_REVIEWED_DISPOSITIONS: dict[str, tuple[str, str]] = {
    "coordinator/bin/assert-no-terminal-plans-in-live.py": (
        "dispatch", "sets a child's PYTHONPATH to the resolved root so the child imports the engine"),
    "coordinator/bin/coordinator-safe-commit.py": (
        "dispatch", "builds a PYTHONPATH=<root> ... coordinator_core.invoke remediation suggestion "
                    "string (both cmd.exe and PowerShell/POSIX spellings) so a human retrying the "
                    "commit sets the child's PYTHONPATH to reach the engine"),
    "coordinator/bin/check-deferral-orphan-memo.py": (
        "dispatch", "passes the root to cc_invoke as the engine to invoke"),
    "coordinator/bin/check-deferral-partial-strangle.py": (
        "dispatch", "passes the root to cc_invoke as the engine to invoke"),
    "coordinator/bin/check-engine-drift.py": (
        "dispatch", "passes the root to cc_invoke as the engine to invoke"),
    "coordinator/bin/coordinator-render-rollup.py": (
        "dispatch", "containment-checks the ALREADY-IMPORTED coordinator_core against the root, "
                    "to catch an ambient module shadowing the resolved engine"),
    "coordinator/bin/handoff-loe-summary.py": (
        "dispatch", "hands the root to engine-side session resolution"),
    "coordinator/bin/lib/op_trampoline.py": (
        "dispatch", "returns the resolved root for the caller's engine import"),
    "coordinator/bin/workday-start-inbox-blitz-assemble.py": (
        "dispatch", "truthiness guard on the resolved root only; no filesystem use"),
    "coordinator/lib/coordinator_session.py": (
        "dispatch", "delegates to _build_subprocess_env, which exports the dispatch answer"),
    "coordinator/scripts/install-maximalist.py": (
        "dispatch", "pip install -e <root> — installs the ENGINE package from that root"),
    "coordinator/tests/test_chunk6_onboarding_setup_doctor.py": (
        "dispatch", "sets a subprocess PYTHONPATH to the engine root"),
    "coordinator/tests/test_percolate_deferred.py": (
        "dispatch", "truthiness guard on the resolved root only"),
    "coordinator/tests/test_scaffold_canonical_structure.py": (
        "dispatch", "sets a subprocess PYTHONPATH to the engine root"),

    "coordinator/bin/check-forwarder-drift.py": (
        "locator", "compares INSTALLED bytes against the source-of-truth copies under "
                   "<root>/coordinator/lib/resolve-claude-klabauter — reads repo content, not the engine "
                   "package. Routing this to the engine accessor would compare the mirror "
                   "against itself and the drift check would pass vacuously."),
    "coordinator/bin/percolate-preflight-scratch-publish.py": (
        "locator", "returns <root>/coordinator as the plugin root; its own error text asks for "
                   "'the claude-klabauter repo root'. Wants the checkout, not the engine."),
    "coordinator/tests/test_workday_evening_tz_coherence.py": (
        "locator", "joins the root to coordinator_core/ops/workday_complete_backfill_scan.py and "
                   "reads it as a read-only structural tripwire against claude-klabauter SOURCE (own comment: "
                   "'read-only against claude-klabauter source'); a second, dispatch-shaped use in the same "
                   "file (env['PYTHONPATH'] = claude_klabauter_root + ...) also resolves the same root, but "
                   "the locator use is the one that must NOT be routed to the engine accessor."),

    "coordinator/lib/resolve-claude-klabauter/_resolve_claude_klabauter.py": (
        "ladder", "the resolution ladder itself — validates a CANDIDATE root's shape "
                  "(<root>/coordinator/bin) before returning it"),
    "coordinator_core/engine_root.py": (
        "ladder", "the C10 accessor; the module every other site is being routed TO"),

    "coordinator/bin/tests/test_delegate_to_gate_root_identity.py": (
        "fixture", "AC12's pin — asserts resolver identity across synthetic roots"),
    "coordinator/bin/tests/test_require_dispatch_engine_on_path.py": (
        "fixture", "pins the C16 seam equal to the inline body it replaces, using a "
                   "monkeypatched resolver and a synthetic root"),
    "coordinator/bin/tests/test_handoff_loe_summary.py": (
        "fixture", "passes a tmp_path root to a formatter under test"),
    "coordinator_core/tests/test_engine_root_two_tier.py": (
        "fixture", "builds synthetic live/published roots to exercise the ladder"),
    "coordinator/bin/tests/test_cc_invoke_provenance_hardening.py": (
        "fixture", "monkeypatches every resolver with a tmp_path or sentinel and asserts which "
                   "axis each cc_invoke entrypoint reads; no resolved root is ever used to reach "
                   "an engine or to read repo content"),
    "coordinator/bin/tests/test_cc_invoke_provenance_reporting_seams.py": (
        "fixture", "same shape — pins each entrypoint to its own resolver by substituting "
                   "distinct dispatch and locator sentinels, precisely because the two ladders "
                   "can return different roots"),

    "coordinator/bin/tests/engine_stamp_probe.py": (
        "dispatch", "answers 'is there a stamped engine on this box' by asking cc_invoke's "
                    "DISPATCH ladder and stat-ing <root>/coordinator_core/_engine_stamp. It "
                    "stats a file, but the root it wants is the dispatch answer -- its own "
                    "docstring refuses to import coordinator_core to ask, because that would "
                    "bind whichever tree pytest put on sys.path first. Routing it to the engine "
                    "accessor is correct, not the silent failure this bucket guards against. "
                    "NOTE: it reaches cc_invoke._resolve_claude_klabauter_root, a PRIVATE name across a "
                    "module boundary -- recorded here so a future cc_invoke refactor has a "
                    "known consumer instead of breaking this probe silently."),
}


def _iter_candidate_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIR_NAMES]
        for name in filenames:
            if Path(name).suffix in _SCAN_EXTENSIONS:
                yield Path(dirpath) / name


def _excluded(rel: str) -> bool:
    return rel.startswith(_EXCLUDE_PREFIXES)


def _axis_use_sites(text: str) -> tuple[list[str], list[str]]:
    """Every use of a name bound to the resolver, split into dispatch-shaped and
    other-shaped use sites.

    Returns (dispatch_uses, other_uses) as `Lnnn: <source line>` strings. An
    empty pair means the resolver result is never bound to a name in this file —
    an inline call, a test asserting on the resolver, or a bare import. Those are
    reported as their own bucket rather than guessed at.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []

    lines = text.splitlines()
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None) or ""
            if name in _RESOLVER_BINDERS:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound.add(target.id)

    dispatch: list[str] = []
    other: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Name):
            continue
        if node.id not in bound or not isinstance(node.ctx, ast.Load):
            continue
        line = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        (dispatch if _DISPATCH_USE.search(line) else other).append(
            f"L{node.lineno}: {line[:120]}"
        )

    # A file that adopted C16's seam and does nothing further with the root has
    # NO use sites at all — the sys.path lines that used to be its evidence are
    # exactly what the collapse deleted. That is the purest dispatch case, not an
    # absence of information, so record the adoption itself as the evidence.
    # Without this the ~190 collapsed files read as "never binds a root".
    if not dispatch and not other and _SEAM_CALL.search(text):
        dispatch.append("adopted require_dispatch_engine_on_path (collapsed by C16)")

    return dispatch, other


def classify(root: Path) -> dict:
    """Walk `root` and assign every env-var-touching file to exactly one bucket.

    Priority order, first match wins — a file that both writes and reads is a
    WRITER, because the export is the behaviour that reaches other processes and
    is therefore the one a routing wave must get right.
    """
    buckets: dict[str, list[dict]] = {
        "b-writer": [],
        "a-dispatch": [],
        "c-locator": [],
        "c-locator-review": [],
        "ladder": [],
        "unbound": [],
    }
    raw_hit_count = 0
    raw_file_count = 0
    skipped_historical = 0

    for path in sorted(_iter_candidate_files(root)):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        hits = 0
        for pat in _WRITER_PATTERNS + _READ_PATTERNS:
            hits += len(pat.findall(text))
        hits += len(_RESOLVER_CALL.findall(text))
        if hits == 0:
            continue

        rel = path.relative_to(root).as_posix()
        if _excluded(rel):
            skipped_historical += 1
            continue

        raw_hit_count += hits
        raw_file_count += 1

        if any(pat.search(text) for pat in _WRITER_PATTERNS):
            buckets["b-writer"].append({"file": rel, "evidence": []})
            continue

        dispatch_uses, other_uses = _axis_use_sites(text)
        if not dispatch_uses and not other_uses:
            buckets["unbound"].append({"file": rel, "evidence": []})
        elif other_uses:
            reviewed = _REVIEWED_DISPOSITIONS.get(rel)
            if reviewed is None:
                buckets["c-locator-review"].append({"file": rel, "evidence": other_uses[:8]})
            else:
                verdict, reason = reviewed
                target = {
                    "dispatch": "a-dispatch",
                    "locator": "c-locator",
                    "ladder": "ladder",
                    "fixture": "unbound",
                }[verdict]
                buckets[target].append(
                    {"file": rel, "evidence": other_uses[:8], "reviewed_because": reason}
                )
        else:
            buckets["a-dispatch"].append({"file": rel, "evidence": []})

    return {
        "root": str(root),
        "raw_hit_count": raw_hit_count,
        "raw_file_count": raw_file_count,
        "skipped_historical": skipped_historical,
        "buckets": {
            "b-writer": {
                "label": "WRITER — exports the variable to child processes",
                "verdict": "route to the C10 write helper; cc_invoke._build_subprocess_env is the highest-value site",
                "file_count": len(buckets["b-writer"]),
                "files": buckets["b-writer"],
            },
            "a-dispatch": {
                "label": "READER, dispatch axis — resolved root used only to reach the engine",
                "verdict": "ENGINE — route to the C10 accessor; no per-file judgement needed",
                "file_count": len(buckets["a-dispatch"]),
                "files": buckets["a-dispatch"],
            },
            "c-locator": {
                "label": "READER, locator axis — reviewed and confirmed a SOURCE-CHECKOUT consumer",
                "verdict": "SOURCE TREE — keep a narrow, honestly-named seam; do NOT route to the "
                           "engine accessor. Each must be greppable per C11: a distinctly-named "
                           "variable or function call, never a bare read of the shared variable.",
                "file_count": len(buckets["c-locator"]),
                "files": buckets["c-locator"],
            },
            "c-locator-review": {
                "label": "READER with a non-dispatch use site and NO recorded disposition",
                "verdict": "REVIEW INDIVIDUALLY, then record the verdict in "
                           "_REVIEWED_DISPOSITIONS. A non-empty bucket here means the census is "
                           "incomplete — C18 must not consume it while it has rows.",
                "file_count": len(buckets["c-locator-review"]),
                "files": buckets["c-locator-review"],
            },
            "ladder": {
                "label": "The resolution machinery itself, not a consumer of it",
                "verdict": "EXCLUDED from routing — these define the ladder C11 routes onto",
                "file_count": len(buckets["ladder"]),
                "files": buckets["ladder"],
            },
            "unbound": {
                "label": "Touches the name but never binds a resolved root",
                "verdict": "mostly tests asserting on the name, and prose; C12's surface, not C11's",
                "file_count": len(buckets["unbound"]),
                "files": buckets["unbound"],
            },
        },
    }


def _wave_partition(files: list[str]) -> list[tuple[str, list[str]]]:
    """Group a bucket's files into the wave directories C11's body names.

    C11 states the directory partition is knowable now; only file-level
    membership within a wave is genuinely unknowable at plan-write time. This
    emits the per-wave FILE LISTS C20's body calls non-optional, because a
    dispatched executor cannot pass a directory argument to pytest and a brief
    without an explicit list degrades invisibly.
    """
    waves = [
        "coordinator_core/ops", "coordinator_core/install",
        "coordinator_core/plugin_health", "coordinator_core/warm",
        "coordinator/bin/lib", "coordinator/bin/tests", "coordinator/bin",
        "coordinator/lib", "coordinator/scripts", "coordinator/tests",
        "bin", "scripts",
    ]
    assigned: dict[str, list[str]] = {w: [] for w in waves}
    other: list[str] = []
    for f in sorted(files):
        for w in waves:
            if f.startswith(w + "/"):
                assigned[w].append(f)
                break
        else:
            other.append(f)
    rows = [(w, fs) for w, fs in assigned.items() if fs]
    if other:
        rows.append(("(unpartitioned)", other))
    return rows


def render_markdown(table: dict) -> str:
    lines = [
        "<!-- Generated by coordinator/bin/classify-env-var-callers.py — do not hand-edit;"
        " regenerate. File lists are a snapshot, not a frozen roster: re-run before using one"
        " as a wave brief. -->",
        "",
        "# Engine-root env var: call-site routing table",
        "",
        "The per-site census C11 routes from and C18 splits by axis. Produced by C20 of"
        " `docs/plans/2026-08-20-an-engine-root-is-not-named-for-the-repo.md`.",
        "",
        f"Measured: **{table['raw_hit_count']}** hits across **{table['raw_file_count']}**"
        f" live files ({table['skipped_historical']} historical-record files excluded).",
        "",
        "## Buckets",
        "",
    ]
    for bucket_id, info in table["buckets"].items():
        lines += [
            f"### `{bucket_id}` — {info['label']}",
            "",
            f"**Verdict:** {info['verdict']}",
            "",
            f"**File count:** {info['file_count']}",
            "",
        ]
        if info["files"]:
            lines.append("<details><summary>Wave partition and file lists</summary>")
            lines.append("")
            for wave, files in _wave_partition([e["file"] for e in info["files"]]):
                lines.append(f"**{wave}** ({len(files)})")
                lines.append("")
                for f in files:
                    lines.append(f"- `{f}`")
                lines.append("")
            lines.append("</details>")
            lines.append("")
        evidenced = [e for e in info["files"] if e["evidence"]]
        if evidenced:
            lines.append("<details><summary>Non-dispatch use sites, with the recorded verdict</summary>")
            lines.append("")
            for entry in evidenced:
                lines.append(f"- `{entry['file']}`")
                if entry.get("reviewed_because"):
                    lines.append(f"  - **Reviewed:** {entry['reviewed_because']}")
                for ev in entry["evidence"]:
                    lines.append(f"  - `{ev}`")
            lines.append("")
            lines.append("</details>")
            lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bucket engine-root env var call sites by axis.")
    parser.add_argument("--root", default=str(_REPO_ROOT_DEFAULT))
    parser.add_argument("--out", default=None, help="write the markdown table to this path")
    parser.add_argument("--json", action="store_true", help="print JSON instead of markdown")
    args = parser.parse_args(argv)

    table = classify(Path(args.root).resolve())
    text = json.dumps(table, indent=2) if args.json else render_markdown(table)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
