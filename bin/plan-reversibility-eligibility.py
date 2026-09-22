"""plan-reversibility-eligibility — D4's six reversibility checks, run mechanically.

WHY THIS EXISTS. `docs/plans/2026-08-30-delegated-approve-for-execution.md` § D4 names six
reversibility preconditions that gate whether a Group EM may delegate-approve a plan for
execution at all. Before this CLI, they existed only as a prose checklist any human or agent
executing the delegated-approve procedure had to read and judge for themselves — the exact
"discharge test" failure this repo's `docs/wiki/invisible-doctrine.md` names: if the operator
remembering to check is the mechanism, the work is not finished. This CLI makes all six checks
codeable, run against the plan's own frontmatter and `## Tasks` spine, with no prose reading
substituting for any of them.

WHY CHECK 3 IS NOT WRITTEN AGAINST `change_kind`. Staff-eng review found the original wording
("irreversible `change_kind`") vacuous: the live `change_kind` enum in `plan-tasks.schema.json`
is a closed 13-value set naming the SURFACE changed (doc-edit, script-edit, config-edit, ...),
never the FLAVOUR of change, and contains none of publish/percolate/release/merge-to-main/
branch-deletion/history-rewrite — so a check written against it could never fire. Check 3 is
restated here against three real, checkable signals instead: a write to a
`coordinator/schemas/*.schema.json` file carrying `x-schema-version` (a schema-version-gate hold
by construction, per `docs/wiki/schema-version-gate.md`), a `scope:`/`writes:` path under the OSS
percolate surface, and a `gated_exit_criteria` row whose `statement` names an external emit using
the same five keyword tokens named above (publish/percolate/release/merge-to-main/branch-deletion/
history-rewrite plus their close spelling variants) — a plan cannot declare a brightline statement
about shipping externally without that language appearing in the statement itself.

WHY THE OSS-PERCOLATE-SURFACE CHECK IS A PATH-PREFIX HEURISTIC, NOT `.percolate-ignore` PARSING.
`coordinator/.percolate-ignore` is a structural leak-DENY list, and its own header says explicitly
it is NOT the boundary deciding which files reach the public mirror for wiki content (that gate is
a separate curated ALLOWLIST in `publish-targets.portable`, per DR-080) — replicating the real
publish-eligibility computation here would require re-implementing `setup/publish.sh`'s allowlist
resolution, which is a different, larger instrument than a mechanical precondition check. This
check instead treats the whole `coordinator/` tree (excluding its own `tests/` subtree, which
never ships per `.percolate-ignore`) as the percolate surface — a conservative, bright-line
approximation consistent with this repo's own doctrine that "`coordinator/` percolates one-way,
DoE->OSS mirror only" (`CLAUDE.md`). Over-flagging here costs the plan a PM turn instead of a
delegated stamp, never a wrong execution — the failure mode this whole gate exists to bias toward.

WHY CHECKS 3 AND 5 SHARE ONE SIGNAL. D4 check 5 ("no peer-vendored schema bump") and half of
check 3 ("no schema-version-gate-holding write") both ultimately ask the same mechanical question
this repo can answer without a registry: does any `writes:` path point at a
`coordinator/schemas/*.schema.json` file that currently carries `x-schema-version`? Every such
schema is, by `docs/wiki/schema-version-gate.md`'s own rule, unconditionally holding on the
x-schema-version axis until any vendoring peer re-vendors it — there is no on-disk registry
distinguishing "peer-vendored" from "not yet vendored but structurally identical," so this CLI
does not invent one. A future registry could split the two signals; until one exists, sharing it
is the conservative direction (a false negative here would silently admit a live gate).

WHY `delegation_declarations` IS READ AS RAW FRONTMATTER, NOT SCHEMA-VALIDATED. Per D4 check 4's
own text: `delegation_declarations` is deliberately NOT added to `plan.schema.json`, because
touching that schema at all trips `claude-klabauter`'s byte-for-byte `check_schema_drift(ref="HEAD")`
regardless of whether the edit is semantic — see finding 0 in this workstream. This CLI reads the
key directly out of the parsed frontmatter mapping and enforces its shape itself.

WHY `--validate-record` LIVES HERE, NOT IN THE JUDGMENT-RECORD SCHEMA (C2). Per staff-eng finding
6: JSON Schema can require a non-empty `evidence` string wherever `score > 0` (C2's schema does
this with `if`/`then`), but it has no way to open a THIRD file and confirm that string is a real,
literal quote from the plan body at `plan_sha` — a schema has no filesystem access. That
verbatim-substring truth check is a validator concern, and this CLI is the validator C2's own
schema comment names.

Zero third-party runtime dependency beyond PyYAML (already imported elsewhere in this directory,
e.g. `approvability-calibration.py`, `compose-review-wave.py`); `git show` is shelled out to only
for `--validate-record`'s historical-content resolution, which cannot be done any other way.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# A console-subsystem child with no console of its own allocates a fresh conhost on Windows, with
# a visible window. `git show` below is short-lived and output-captured. 0 on POSIX.
_NO_CONSOLE: Dict[str, Any] = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

_TASKS_FENCE = re.compile(
    r"^## Tasks\s*\n+```yaml plan-tasks\s*\n(.*?)\n```", re.MULTILINE | re.DOTALL
)

# The five irreversible-action tokens named in D4 check 3's own prose, plus close spelling
# variants, used to scan a gated_exit_criteria row's `statement` for external-emit language.
_EXTERNAL_EMIT_TOKENS = (
    "publish",
    "percolate",
    "release",
    "merge-to-main",
    "merge to main",
    "branch-deletion",
    "branch deletion",
    "history-rewrite",
    "history rewrite",
    "external emit",
    "external-emit",
)


class PlanReadError(ValueError):
    """Raised when the plan document cannot be read/parsed into the shapes this CLI needs."""


def _load_plan_text(plan_path: Path) -> str:
    try:
        return plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanReadError(f"cannot read plan {plan_path}: {exc}") from exc


def _parse_frontmatter(text: str, plan_path: Path) -> dict[str, Any]:
    if not text.startswith("---"):
        raise PlanReadError(f"{plan_path} has no YAML frontmatter (expected leading '---')")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise PlanReadError(f"{plan_path} frontmatter is not closed with a second '---'")
    try:
        import yaml
    except ImportError:  # pragma: no cover - environment defect, not a code path under test
        raise PlanReadError("PyYAML is not installed; cannot parse plan frontmatter")
    try:
        parsed = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise PlanReadError(f"{plan_path} frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PlanReadError(f"{plan_path} frontmatter did not parse to a mapping")
    return parsed


def _parse_tasks(text: str, plan_path: Path) -> list[dict[str, Any]]:
    """The `## Tasks` fenced `plan-tasks` block, per `docs/wiki/writing-plans.md`.

    A plan with no such block yet (still in Phase 1 authoring) parses to an empty task list
    rather than raising — an author has not necessarily reached `## Tasks` yet, and an empty
    spine is handled the same as a spine with no writes at all: containment checks vacuously
    hold, and check 4 (delegation_declarations) still gates independently.
    """
    match = _TASKS_FENCE.search(text)
    if not match:
        return []
    try:
        import yaml
    except ImportError:  # pragma: no cover - environment defect, not a code path under test
        raise PlanReadError("PyYAML is not installed; cannot parse the plan-tasks block")
    try:
        parsed = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise PlanReadError(f"{plan_path} plan-tasks block is not valid YAML: {exc}") from exc
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise PlanReadError(f"{plan_path} plan-tasks block did not parse to a list")
    return [row for row in parsed if isinstance(row, dict)]


def _all_write_paths(tasks: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for row in tasks:
        writes = row.get("writes")
        if isinstance(writes, list):
            paths.extend(str(p) for p in writes if isinstance(p, str))
    return paths


def _scope_paths(frontmatter: dict[str, Any]) -> list[str]:
    scope = frontmatter.get("scope")
    if isinstance(scope, list):
        return [str(p) for p in scope if isinstance(p, str)]
    return []


def _resolves_inside_worktree(repo_root: Path, rel_path: str) -> bool:
    if not rel_path or Path(rel_path).is_absolute():
        return False
    if rel_path.startswith("~"):
        return False
    resolved = (repo_root / rel_path).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True


def _is_cross_repo_or_archive_or_peer(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").lstrip("/")
    segments = normalized.split("/")
    first_segment = segments[0] if segments else ""
    if first_segment in ("cross-repo", "archive"):
        return True
    return first_segment == "state" and len(segments) > 1 and segments[1] == "cross-repo"


def _schema_has_version_gate(repo_root: Path, rel_path: str) -> bool:
    """True iff `rel_path` names a `coordinator/schemas/*.schema.json` file this repo's own
    working tree carries an `x-schema-version` key in — the schema-version-gate holding signal
    shared by D4 checks 3 and 5 (see module docstring)."""
    normalized = rel_path.replace("\\", "/")
    if not normalized.startswith("coordinator/schemas/") or not normalized.endswith(".json"):
        return False
    target = repo_root / Path(normalized)
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        # A schema path that does not exist yet cannot be a live version-gate hold. A plan
        # authoring a brand-new schema file has nothing on disk to check yet.
        return False
    return '"x-schema-version"' in content


def _under_oss_percolate_surface(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").lstrip("/")
    if not normalized.startswith("coordinator/"):
        return False
    return not normalized.startswith("coordinator/tests/")


def _names_external_emit(statement: str) -> bool:
    lowered = statement.lower()
    return any(token in lowered for token in _EXTERNAL_EMIT_TOKENS)


def _gated_exit_criteria_statements(frontmatter: dict[str, Any]) -> list[str]:
    rows = frontmatter.get("gated_exit_criteria")
    if not isinstance(rows, list):
        return []
    return [
        str(row.get("statement", ""))
        for row in rows
        if isinstance(row, dict) and row.get("statement")
    ]


def compute_reversibility(repo_root: Path, plan_path: Path) -> dict[str, Any]:
    """Compute C2's `reversibility` object for `plan_path`. Raises `PlanReadError` on a plan
    this CLI cannot parse at all — a distinct failure mode from "parses but ineligible"."""
    text = _load_plan_text(plan_path)
    frontmatter = _parse_frontmatter(text, plan_path)
    tasks = _parse_tasks(text, plan_path)

    write_paths = _all_write_paths(tasks)
    scope_paths = _scope_paths(frontmatter)

    # Check 1
    writes_inside_worktree = all(_resolves_inside_worktree(repo_root, p) for p in write_paths)

    # Check 2
    no_cross_repo_or_archive_writes = not any(
        _is_cross_repo_or_archive_or_peer(p) for p in write_paths
    )

    # Check 3
    no_schema_version_gate_write = not any(
        _schema_has_version_gate(repo_root, p) for p in write_paths
    )
    no_percolate_surface_scope = not any(
        _under_oss_percolate_surface(p) for p in (write_paths + scope_paths)
    )
    no_external_emit_criterion = not any(
        _names_external_emit(s) for s in _gated_exit_criteria_statements(frontmatter)
    )
    no_irreversible_surface = (
        no_schema_version_gate_write and no_percolate_surface_scope and no_external_emit_criterion
    )

    # Check 4
    declarations = frontmatter.get("delegation_declarations")
    delegation_declarations_present = (
        isinstance(declarations, dict)
        and "external_actions" in declarations
        and "destructive_git" in declarations
        and declarations.get("external_actions") is not None
        and declarations.get("destructive_git") is not None
    )

    # Check 5 (shares the schema-version-gate signal with check 3 — see module docstring)
    no_peer_vendored_schema_bump = not any(
        _schema_has_version_gate(repo_root, p) for p in write_paths
    )

    # Check 6
    delegation_declarations_clean = False
    if delegation_declarations_present:
        declared = declarations or {}
        delegation_declarations_clean = (
            declared.get("external_actions") == "none"
            and declared.get("destructive_git") == "none"
        )

    eligible = (
        writes_inside_worktree
        and no_cross_repo_or_archive_writes
        and no_irreversible_surface
        and delegation_declarations_present
        and no_peer_vendored_schema_bump
        and delegation_declarations_clean
    )

    return {
        "writes_inside_worktree": writes_inside_worktree,
        "no_cross_repo_or_archive_writes": no_cross_repo_or_archive_writes,
        "no_irreversible_surface": no_irreversible_surface,
        "delegation_declarations_present": delegation_declarations_present,
        "no_peer_vendored_schema_bump": no_peer_vendored_schema_bump,
        "delegation_declarations_clean": delegation_declarations_clean,
        "eligible": eligible,
    }


def _git_show(repo_root: Path, sha: str, rel_path: str) -> Optional[str]:
    """`git show <sha>:<rel_path>`, or None if the revision/path cannot be resolved."""
    try:
        proc = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(repo_root), "show", f"{sha}:{rel_path}"],
            capture_output=True,
            text=True,
            check=False,
            **_NO_CONSOLE,
        )
    except (OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def validate_record(repo_root: Path, record_path: Path) -> tuple[bool, list[str]]:
    """Per staff-eng finding 6: reject a judgment record unless every dimension scored above 0
    carries an `evidence` string occurring as a literal substring of the plan body resolved at
    the record's own `plan_sha`. Returns (ok, problems)."""
    problems: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return False, [f"cannot read {record_path}: {exc}"]
    except json.JSONDecodeError as exc:
        return False, [f"{record_path} is not valid JSON: {exc}"]
    if not isinstance(record, dict):
        return False, [f"{record_path} did not parse to a JSON object"]

    plan_path = record.get("plan_path")
    plan_sha = record.get("plan_sha")
    if not plan_path or not plan_sha:
        return False, ["record is missing plan_path and/or plan_sha"]

    plan_body = _git_show(repo_root, str(plan_sha), str(plan_path))
    if plan_body is None:
        return False, [f"cannot resolve {plan_path} at {plan_sha} via git show"]

    scores = record.get("scores")
    if not isinstance(scores, list):
        return False, ["record has no scores array"]

    for entry in scores:
        if not isinstance(entry, dict):
            problems.append(f"scores entry {entry!r} is not an object")
            continue
        score = entry.get("score")
        if not isinstance(score, (int, float)) or score <= 0:
            continue
        evidence = entry.get("evidence")
        dimension = entry.get("dimension", "<unnamed>")
        if not isinstance(evidence, str) or not evidence:
            problems.append(f"{dimension}: score {score} carries no evidence string")
            continue
        if evidence not in plan_body:
            problems.append(
                f"{dimension}: evidence quote is not a literal substring of "
                f"{plan_path}@{plan_sha}"
            )

    return (len(problems) == 0), problems


def _repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path.cwd()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan_path", nargs="?", help="path to the plan markdown file")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--repo-root", help="repo root; default is the current working directory")
    parser.add_argument(
        "--validate-record",
        metavar="JUDGMENT_RECORD_PATH",
        help="validate a judgment record's verbatim-substring evidence instead of computing "
        "reversibility for a plan",
    )
    args = parser.parse_args(argv)

    repo_root = _repo_root(args.repo_root)

    if args.validate_record:
        ok, problems = validate_record(repo_root, Path(args.validate_record))
        if args.json:
            print(json.dumps({"valid": ok, "problems": problems}, indent=2))
        else:
            if ok:
                print(f"{args.validate_record}: valid — every evidence quote is verbatim.")
            else:
                print(f"{args.validate_record}: INVALID")
                for problem in problems:
                    print(f"  - {problem}")
        return 0 if ok else 1

    if not args.plan_path:
        parser.error("plan_path is required unless --validate-record is given")

    plan_path = Path(args.plan_path)
    if not plan_path.is_absolute():
        plan_path = repo_root / plan_path

    try:
        reversibility = compute_reversibility(repo_root, plan_path)
    except PlanReadError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(reversibility, indent=2))
    else:
        for key, value in reversibility.items():
            print(f"{key}: {value}")

    return 0 if reversibility["eligible"] else 1


if __name__ == "__main__":
    sys.exit(main())
