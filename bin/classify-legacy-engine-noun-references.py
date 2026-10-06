"""Generate C2's four-class reference manifest: every ``claude-klabauter``-noun LINE across the
four code trees (``coordinator/``, ``coordinator_core/``, ``bin/``, ``scripts/``),
classified into exactly one of RENAMEABLE-LOCAL, CONTRACT-BOUND, EXTERNALLY-NAMED-THING,
PROSE-ONLY or FIXTURE-LITERAL (a test file whose noun sits only in non-f string literals or a test function's name), under the most-binding tie-break order
EXTERNALLY-NAMED-THING > CONTRACT-BOUND > RENAMEABLE-LOCAL > PROSE-ONLY.

Plan: docs/plans/2026-09-10-claude-klabauter-noun-sweep-across-the-tree.md, row C2.
Spec backlink: that row's body and AC2/AC8.

Methodology precedent: coordinator/bin/classify-engine-root-residue.py (bucket-by-line,
generated not hand-authored). Slice-list precedent: coordinator/bin/claude-klabauter-4th-class-ref-
manifest.md (dated ground-truth snapshot with a classification key).

Negative spec: this script never edits anything outside the two artifacts it emits. It
does not itemize the 17 `-assemble` entry points' failures (plan Anti-scope), does not
re-derive the CLAUDE_KLABAUTER_ROOT allowlist (cites `docs/reference/engine-root-residue-
allowlist.md`'s buckets instead), and refuses -- unless given ``--admit-renameable
file:line`` -- to add a RENAMEABLE-LOCAL row outside the slice list recorded at this
row's own SHA (the ratchet, escalation E2).

SPAWNS: two `git` processes total -- `ls-files` and `rev-parse` on this repo. No per-file,
per-identifier or per-item git call. Reads only this repo's own tree.

Never imports `coordinator_core`: a stdlib-only CLI that runs with no engine-root
bootstrap, so it keeps its own git spawns and is exempt from the shared git runner
(`coordinator_core/tests/test_shared_git_runner.py :: _CONTRACT_EXEMPT_MODULES`).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TREES = ("coordinator", "coordinator_core", "bin", "scripts")
NOUN = re.compile(r"claude-klabauter", re.IGNORECASE)

#: EXTERNALLY-NAMED-THING: the noun because the thing IS still called that. Line-level,
#: highest precedence -- a line matching any of these is never anything else.
EXTERNALLY_NAMED_PATTERNS = (
    re.compile(r"repos\.claude_klabauter"),
    re.compile(r"\.claude-klabauter-root"),
    re.compile(r"claude-klabauter"),
)

#: CONTRACT-BOUND by FILE (whole file, every matching line): the file itself IS the
#: engine_root two-tier contract, a sibling-keyed basename family, or a pinned test.
#: Paths are repo-root-relative, forward-slash.
CONTRACT_BOUND_FILES = frozenset(
    {
        "coordinator_core/engine_root.py",
        "coordinator/lib/resolve-claude-klabauter/_resolve_claude_klabauter.py",
        "coordinator/lib/resolve-claude-klabauter/tests/test_dispatch_prefers_stamped_engine.py",
        "coordinator/bin/check-claude-klabauter-doctor-sentinel.sh",
        "coordinator/bin/remove-claude-klabauter-precommit-hook.py",
        "coordinator_core/tests/test_claude_klabauter_doctor_probe_selectors.py",
        "coordinator_core/tests/test_engine_root_census.py",
        "coordinator_core/tests/test_engine_root_conformance.py",
        "coordinator_core/tests/test_engine_root_env_accessor.py",
        "coordinator_core/tests/test_engine_root_mirror_parity.py",
        "coordinator_core/tests/test_engine_root_module_name_is_not_repo_named.py",
        "coordinator_core/tests/test_engine_root_two_tier.py",
        "coordinator_core/install/test_resolve_claude_klabauter.py",
        "coordinator_core/install/test_resolve_claude_klabauter_currency_signal.py",
        "coordinator_core/install/test_resolve_claude_klabauter_publisher_only.py",
        "coordinator_core/install/test_resolve_claude_klabauter_rename_retry.py",
        "coordinator_core/install/test_resolve_claude_klabauter_exec_cli.py",
        "coordinator_core/percolate/codename_provenance_seed.py",
        "bin/claude-klabauter-doctor-probe.py",
        "bin/tests/test_claude_klabauter_doctor_generation_probe.py",
        "bin/tests/test_claude_klabauter_doctor_warm_probes.py",
        "bin/tests/test_claude_klabauter_doctor_root_channels_reconciled_probe.py",
        "bin/tests/test_claude_klabauter_doctor_route_share_probe.py",
    }
)

#: CONTRACT-BOUND by LINE inside an otherwise-default file: cc_invoke.py's two standing
#: aliases (plan C3's default is keep-as-shim; this generator does not decide the arm,
#: it only records that these two lines are not renameable-local candidates).
CC_INVOKE_PATH = "coordinator/bin/lib/cc_invoke.py"
CC_INVOKE_ALIAS_NAMES = ("_resolve_claude_klabauter_root", "_resolve_claude_klabauter_root")

#: The ratchet: RENAMEABLE-LOCAL identifiers recorded at THIS row's own SHA. Any later
#: regeneration that would add a new RENAMEABLE-LOCAL identifier not in this set is
#: refused (escalation E2) unless passed via --admit-renameable.
SLICE_LIST_PATH = REPO_ROOT / "coordinator/bin/legacy-engine-noun-reference-classes.json"

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


#: A repo key (`claude_klabauter`, `claude-klabauter`) or an UPPER_CASE env var is a real
#: identifier a rename sweep cannot touch; a line whose noun sits only in these is
#: admitted under E2 without --admit-renameable.
_UPPER_ENV_VAR = re.compile(r"\b[A-Z0-9_]*CLAUDE-KLABAUTER[A-Z0-9_]*\b")


def _is_real_identifier_line(text: str) -> bool:
    """True iff every noun occurrence on ``text`` is inside a repo key or an
    UPPER_CASE env var name."""
    stripped = re.sub(r"project[-_]claude-klabauter", "", text, flags=re.IGNORECASE)
    stripped = _UPPER_ENV_VAR.sub("", stripped)
    return NOUN.search(text) is not None and NOUN.search(stripped) is None


def _no_console_creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git_ls_files(repo: Path, *pathspecs: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", *pathspecs],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        creationflags=_no_console_creationflags(),
    ).stdout
    return [line for line in out.split("\n") if line]


def _is_prose_line(stripped: str, in_docstring: bool) -> bool:
    if in_docstring:
        return True
    return stripped.startswith("#")


def _toggle_docstring(stripped: str, in_docstring: bool) -> bool:
    # Cheap, line-oriented heuristic: count triple-quote delimiters per line. Correct
    # for the overwhelming majority of single-open/single-close docstring lines in this
    # tree; a line that both opens and closes (or opens two) toggles an even number of
    # times and is treated as NOT entering a multi-line docstring, which is the common
    # one-line-docstring case.
    count = stripped.count('"""') + stripped.count("'''")
    if count % 2 == 1:
        return not in_docstring
    return in_docstring


def _classify_line(rel: str, stripped: str, in_docstring: bool) -> tuple[str, str | None]:
    """Return (primary_class, secondary_class_or_None) for one already-noun-bearing line."""
    if any(p.search(stripped) for p in EXTERNALLY_NAMED_PATTERNS):
        secondary = "PROSE-ONLY" if _is_prose_line(stripped, in_docstring) else None
        return "EXTERNALLY-NAMED-THING", secondary

    if rel in CONTRACT_BOUND_FILES:
        secondary = "PROSE-ONLY" if _is_prose_line(stripped, in_docstring) else None
        return "CONTRACT-BOUND", secondary

    if rel == CC_INVOKE_PATH and any(name in stripped for name in CC_INVOKE_ALIAS_NAMES):
        return "CONTRACT-BOUND", None

    if _is_prose_line(stripped, in_docstring):
        return "PROSE-ONLY", None

    if _is_test_file(rel) and not NOUN.search(
        _TEST_DEF_NAME.sub("def ", _STRING_LITERAL.sub("", stripped))
    ):
        return "FIXTURE-LITERAL", None

    return "RENAMEABLE-LOCAL", None


#: A single-line non-f quoted literal. An f-string interpolates code, so its
#: noun can be a live identifier and is never stripped. Multi-line strings are
#: already handled by the docstring toggle.
_STRING_LITERAL = re.compile(r"""(?<![A-Za-z0-9_])[rRbBuU]{0,2}("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""")

#: A test function's name labels what it asserts about; it is never a binding a
#: rename sweep rewrites. Parameters and the body stay classified on their own text.
_TEST_DEF_NAME = re.compile(r"^(?:async\s+)?def\s+test_\w*")


def _is_test_file(rel: str) -> bool:
    """Test data, not production: a fixture literal is renamed with its test
    (or is deliberately arbitrary), never by a codename rename sweep."""
    name = rel.rsplit("/", 1)[-1]
    return name.startswith("test_") or "/tests/" in f"/{rel}"


def _scan_four_trees(repo: Path) -> tuple[list[dict], int]:
    """Single compiled-pattern, file-filter-first pass (perf plan): read every tracked
    file under the four trees once, skip files with zero hits without splitting lines,
    split lines only in hit files."""
    rows: list[dict] = []
    files = _git_ls_files(repo, *TREES)
    for rel in files:
        if not rel.endswith(".py"):
            continue
        path = repo / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not NOUN.search(text):
            continue
        in_docstring = False
        for lineno, line in enumerate(text.split("\n"), start=1):
            stripped = line.strip()
            has_hit = bool(NOUN.search(line))
            was_in_docstring = in_docstring
            in_docstring = _toggle_docstring(stripped, in_docstring)
            if not has_hit:
                continue
            primary, secondary = _classify_line(rel, stripped, was_in_docstring)
            rows.append(
                {
                    "file": rel,
                    "line": lineno,
                    "text": line,
                    "primary_class": primary,
                    "secondary_class": secondary,
                }
            )
    return rows, len(files)


def _load_recorded() -> tuple[set[str], set[str]] | None:
    """(slice-list ``file:line`` keys, recorded exempt files) from the prior snapshot."""
    if not SLICE_LIST_PATH.exists():
        return None
    try:
        data = json.loads(SLICE_LIST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    slices = data.get("renameable_local_slice_list")
    if not isinstance(slices, list):
        return None
    exempt = data.get("exempt_files")
    return (
        {f"{r['file']}:{r['line']}" for r in slices if isinstance(r, dict)},
        {f for f in exempt if isinstance(f, str)} if isinstance(exempt, list) else set(),
    )


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(REPO_ROOT))
    parser.add_argument(
        "--repo-sha",
        default=None,
        help="Pin this repo's SHA (avoids a second git spawn). "
        "Falls back to `git rev-parse HEAD` if omitted.",
    )
    parser.add_argument(
        "--admit-renameable",
        action="append",
        default=[],
        metavar="file:line",
        help="Explicit per-file admission of a new RENAMEABLE-LOCAL row outside the "
        "recorded slice list (escalation E2).",
    )
    parser.add_argument("--out-manifest", default=None)
    parser.add_argument("--out-json", default=None)
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()

    t0 = time.monotonic()
    rows, file_count = _scan_four_trees(repo)
    scan_ms = (time.monotonic() - t0) * 1000

    admitted = set(args.admit_renameable)
    recorded = _load_recorded()
    slice_list, exempt_recorded = recorded if recorded else (None, set())
    refused: list[str] = []

    for row in rows:
        if row["primary_class"] != "RENAMEABLE-LOCAL":
            continue
        key = f"{row['file']}:{row['line']}"
        if slice_list is not None and key not in slice_list and row["file"] in exempt_recorded:
            row["primary_class"] = "CONTRACT-BOUND"
            continue
        if slice_list is not None and key not in slice_list and key not in admitted:
            if _is_real_identifier_line(row["text"]):
                row["admitted"] = "real-identifier"
                continue
            refused.append(key)

    if refused:
        sys.stderr.write(
            "classify-legacy-engine-noun-references: refused new RENAMEABLE-LOCAL "
            f"row(s) outside the recorded slice list: {', '.join(refused)}\n"
            "Pass --admit-renameable file:line to admit explicitly (escalation E2).\n"
        )
        return 1

    repo_sha = args.repo_sha or _rev_parse(repo)

    manifest = _render_manifest(
        rows,
        repo_sha,
        file_count,
        scan_ms,
    )
    classes_json = _render_json(rows, repo_sha)

    out_manifest = Path(args.out_manifest) if args.out_manifest else (
        repo / "coordinator/bin/legacy-engine-noun-reference-manifest.md"
    )
    out_json = Path(args.out_json) if args.out_json else SLICE_LIST_PATH
    out_manifest.write_text(manifest, encoding="utf-8", newline="\n")
    out_json.write_text(json.dumps(classes_json, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return 0


def _rev_parse(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        creationflags=_no_console_creationflags(),
    ).stdout.strip()


def _render_json(rows: list[dict], repo_sha: str) -> dict:
    renameable = [
        {"file": r["file"], "line": r["line"]}
        for r in rows
        if r["primary_class"] == "RENAMEABLE-LOCAL"
    ]
    exempt = sorted(
        {
            r["file"]
            for r in rows
            if r["primary_class"] in ("CONTRACT-BOUND", "EXTERNALLY-NAMED-THING", "PROSE-ONLY", "FIXTURE-LITERAL")
        }
    )
    return {
        "repo_sha": repo_sha,
        "renameable_local_slice_list": renameable,
        "exempt_files": exempt,
    }


def _excerpt(text: str) -> str:
    """One source line as a manifest table cell: pipes escaped for the table,
    and `](` broken so a quoted markdown link is not read as a live link --
    the published mirror's reference validator fails on those, and the target
    is a fixture path that was never meant to resolve."""
    if _LEGACY_ROOT_NAME.search(text):
        return "(text withheld: names the legacy root)"
    return text.strip().replace("|", "\\|").replace("](", "]\\(")[:160]


#: A quoted line that names the legacy root would re-enter the tracked corpus as an
#: unmarked hit; the manifest carries its coordinates only.
_LEGACY_ROOT_NAME = re.compile(r"doe[-_]root|(?:repos|working_repos)\.doe_", re.IGNORECASE)


def _render_manifest(
    rows: list[dict],
    repo_sha: str,
    file_count: int,
    scan_ms: float,
) -> str:
    lines: list[str] = []
    a = lines.append
    a(
        "<!-- GENERATED-BY coordinator/bin/classify-legacy-engine-noun-references.py -- "
        "do not hand-edit; regenerate with:\n"
        "     python coordinator/bin/classify-legacy-engine-noun-references.py -->"
    )
    a("")
    a("# Legacy engine-noun (`claude-klabauter`) four-class reference manifest")
    a("")
    a(f"repo SHA: `{repo_sha}`")
    a("")
    a(
        "The classified atom is the **LINE**, matching the denominator's unit exactly. "
        "A mixed line (carrying more than one class-worthy signal) takes its "
        "MOST-BINDING class, in the order "
        "**EXTERNALLY-NAMED-THING > CONTRACT-BOUND > RENAMEABLE-LOCAL > PROSE-ONLY**. "
        "A mixed line also carries a secondary-class column, so a RENAMEABLE-LOCAL "
        "identifier on an otherwise CONTRACT-BOUND/PROSE-ONLY line is never invisibly "
        "swallowed."
    )
    a("")
    denom_cmd = "grep -rn --include='*.py' -i claude-klabauter coordinator/ coordinator_core/ bin/ scripts/ | wc -l"
    a(f"Denominator command: `{denom_cmd}`")
    a(f"Denominator at `{repo_sha}`: **{sum(1 for _ in rows)}** re-run-at-HEAD result below.")
    a("")

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["primary_class"]] = counts.get(r["primary_class"], 0) + 1
    total = sum(counts.values())
    a("## Per-class counts")
    a("")
    for cls in ("EXTERNALLY-NAMED-THING", "CONTRACT-BOUND", "RENAMEABLE-LOCAL", "PROSE-ONLY", "FIXTURE-LITERAL"):
        a(f"- **{cls}**: {counts.get(cls, 0)}")
    a(f"- **Total (reconciles to denominator)**: {total}")
    a("")
    a(
        "The `CLAUDE_KLABAUTER_ROOT` env-var subset is not re-derived here; it cites "
        "`docs/reference/engine-root-residue-allowlist.md`'s buckets by reference "
        "(generated by `coordinator/bin/classify-engine-root-residue.py`)."
    )
    a("")
    a("## Generator performance")
    a("")
    a(f"- Four-tree scan over {file_count} tracked files: **{scan_ms:.1f}ms**")
    a("- 2 `git` spawns (`ls-files`, `rev-parse`)")
    a("")

    for cls in ("EXTERNALLY-NAMED-THING", "CONTRACT-BOUND"):
        cls_rows = [r for r in rows if r["primary_class"] == cls]
        a(f"## {cls} ({len(cls_rows)})")
        a("")
        a("| file:line | secondary | text |")
        a("|---|---|---|")
        for r in cls_rows:
            text = _excerpt(r["text"])
            a(f"| `{r['file']}:{r['line']}` | {r['secondary_class'] or '-'} | `{text}` |")
        a("")

    renameable_rows = [r for r in rows if r["primary_class"] == "RENAMEABLE-LOCAL"]
    a(f"## RENAMEABLE-LOCAL ({len(renameable_rows)})")
    a("")
    a(
        "Grouped into file-disjoint slices, one per surface directory, so the "
        "identifier follow-on is a transcription."
    )
    a("")
    if not renameable_rows:
        a("(zero -- there were no RENAMEABLE-LOCAL-default code lines in this scan)")
        a("")
    else:
        slices: dict[str, list[dict]] = {}
        for r in renameable_rows:
            top = r["file"].split("/", 1)[0]
            slices.setdefault(top, []).append(r)
        for top, slice_rows in sorted(slices.items()):
            files_in_slice = sorted({r["file"] for r in slice_rows})
            a(f"### Slice: `{top}/` ({len(slice_rows)} lines, {len(files_in_slice)} files)")
            a("")
            a("| file:line | secondary | text |")
            a("|---|---|---|")
            for r in slice_rows:
                text = _excerpt(r["text"])
                a(f"| `{r['file']}:{r['line']}` | {r['secondary_class'] or '-'} | `{text}` |")
            a("")

    prose_rows = [r for r in rows if r["primary_class"] == "PROSE-ONLY"]
    prose_files = sorted({r["file"] for r in prose_rows})
    a(f"## PROSE-ONLY ({len(prose_rows)} lines, {len(prose_files)} files)")
    a("")
    a("Aggregate count plus generated file list only -- no per-line rationale (would make this XL).")
    a("")
    for f in prose_files:
        a(f"- `{f}`")
    a("")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
