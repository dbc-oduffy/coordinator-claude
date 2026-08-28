"""coordinator/bin/publish-allowlist-generate.py — derives field 7 (the
allowlist CSV) of the two `claude-klabauter*` rows in
`setup/publish-targets.portable` from `setup/publish-allowlist-declarations.
yaml`, mechanically, rather than by hand-edit.

Purpose: `setup/publish-targets.portable`'s field 7 has drifted silently
before (2026-08-19: 708 inclusions against 948 tracked, withholding 240 CLIs
including the warm engine's own operator stop hatch) because nothing forced
every git-tracked top-level name under a row's source dir to be CLASSIFIED —
admitted or denied — before the file was hand-edited. This script closes that
gap for the two `claude-klabauter` / `claude-klabauter-coordinator-bin` rows:
it reads `setup/publish-allowlist-declarations.yaml`'s `deny` and
`include_root` lists for a row, asserts they are disjoint and their union
covers every `git ls-files`-tracked top-level name under that row's source
dir (AC15 — a name in NEITHER declaration is a hard error naming the file,
never a silent omission), and regenerates the row's field-7 CSV as
`sorted(include_root)` followed by the row's EXISTING `!`-prefixed narrow
exclusions carried over verbatim (this script never re-derives the deny-
segment/fixture-tree narrows already hand-authored on the row — see each
row's own comment block in `setup/publish-targets.portable` for those).

Never enumerates the filesystem (`os.walk`) as the mechanism that DISCOVERS
what a row could ship — `git ls-files` only, so an untracked `.bak` sitting
in a source dir can never surface as a candidate allowlist entry. Enumeration
inside a value the declarations already named (verifying an include-root's
own membership is real, non-empty, tracked content) is fine; enumeration AS
the classifier is exactly the hazard AC10 forbids (see the plan; also why
this script never imports `coordinator_core.ops` or roots anything at the op
registry — `percolate.run` / `percolate.validate_store` are eagerly imported
by `ops/__init__.py`, and importing that package here would silently re-admit
the never-published `percolate` package via a "trustworthy" derived path).

Two AC9 contract roots are asserted present under their declared,
directory-granular include-root parent on every run, for the engine row
only, hard-erroring (never merely warning) if either is missing:
    - `frontmatter/schema_validate.py` (DoE resolves it BY FILE PATH)
    - `contract/cockpit_schema/emit_schema.py` (claude-central-em's sole
      regeneration path for their frozen schema)
Both sit under an already-admitted directory (`frontmatter`, `contract`)
precisely because AC9 requires directory-granular emission for the seven
sibling-visible names — a future edit that narrows either directory entry to
individual files could silently drop these two with a green claude-klabauter suite and
a broken box; this assertion is what turns that drop into a hard failure
here instead.

Usage:
    publish-allowlist-generate.py            regenerate both rows' field 7 in
                                              place, print a per-row diff
                                              summary (names added/removed).
    publish-allowlist-generate.py --check    exit 0 if the freshly generated
                                              CSV equals what is already on
                                              disk for both rows (idempotent),
                                              exit 1 and print the divergence
                                              otherwise. Writes nothing.

Negative-spec:
    - Does NOT compute the bin row's reachability-import closure at runtime.
      That computation (which `coordinator/bin` CLIs' `coordinator_core.*`
      import closure reaches an engine-row-denied package) was performed
      once, by hand, to author `setup/publish-allowlist-declarations.yaml`'s
      `claude-klabauter-coordinator-bin.deny` list — see that list's own
      comment for the rule and the 2026-08-20 count it produced. Re-deriving
      it here on every run would just re-read the same input a second way,
      at real per-run cost, for a rule that does not change between runs
      unless a human re-authors the yaml.
    - Does NOT touch the declarations yaml. It is this script's INPUT, hand-
      authored, never generated output — see that file's own header.
    - Does NOT run a publish round or touch `coordinator/lib/percolate/*`.
      Regenerating field 7 is authoring, not publishing.

Spec backlink: docs/plans/2026-08-20-the-publish-allowlist-stops-being-hand-m.md
               chunk C4 (AC8, AC9, AC10, AC11, AC12, AC15).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PORTABLE_PATH = _REPO_ROOT / "setup" / "publish-targets.portable"
_DECLARATIONS_PATH = _REPO_ROOT / "setup" / "publish-allowlist-declarations.yaml"

#: `(row_name, source_subdir)` — the two rows this script derives field 7 for.
_ROWS: List[Tuple[str, str]] = [
    ("claude-klabauter", "coordinator_core"),
    ("claude-klabauter-coordinator-bin", "coordinator/bin"),
]

#: Field index of the allowlist CSV in a `publish-targets.portable` row —
#: `name|mode|dest_sigil|source_subdir|dest_subdir|native_slugs|allowlist`.
_ALLOWLIST_FIELD = 6

#: AC9 — directory-granular sibling-visible names. Narrowing any of these to
#: file granularity is the exact hazard this constant's callers guard
#: against (see module docstring).
_DIRECTORY_GRANULAR_NAMES = frozenset(
    {"hooks", "ops", "write_guards", "bash_guards", "frontmatter", "session", "contract"}
)

#: AC9 — explicit contract roots no import closure can discover, asserted
#: present under their declared directory-granular parent on every run.
#: `(repo-relative path, owning include-root parent name)`.
_CONTRACT_ROOTS: List[Tuple[str, str]] = [
    ("coordinator_core/frontmatter/schema_validate.py", "frontmatter"),
    ("coordinator_core/contract/cockpit_schema/emit_schema.py", "contract"),
]


class GeneratorError(Exception):
    """A row's declarations do not cover its tracked top-level names, or a
    disjointness/contract-root invariant failed — always hard, never a
    warning (AC15's "deny-by-default... not opt-out")."""


def _git_ls_files(subdir: str) -> List[str]:
    import subprocess

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["git", "ls-files", "--", subdir],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
        creationflags=no_window,
    )
    return [line for line in result.stdout.splitlines() if line]


def _tracked_top_level_names(source_subdir: str) -> List[str]:
    """Distinct top-level names directly under `source_subdir`, from
    `git ls-files` only (never the filesystem — see module docstring)."""
    prefix_depth = len(Path(source_subdir).parts)
    names = set()
    for rel_posix in _git_ls_files(source_subdir):
        parts = Path(rel_posix).parts
        if len(parts) <= prefix_depth:
            continue
        names.add(parts[prefix_depth])
    return sorted(names)


def _load_declarations() -> Dict:
    import yaml

    with open(_DECLARATIONS_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "rows" not in data:
        raise GeneratorError(
            f"{_DECLARATIONS_PATH} does not carry a top-level 'rows' mapping"
        )
    return data["rows"]


def _row_declarations(rows: Dict, row_name: str) -> Tuple[List[str], List[str]]:
    row = rows.get(row_name)
    if row is None:
        raise GeneratorError(f"{_DECLARATIONS_PATH} declares no '{row_name}' row")
    deny_entries = row.get("deny") or []
    deny_names = sorted(
        entry["name"] if isinstance(entry, dict) else entry for entry in deny_entries
    )
    include_root = sorted(row.get("include_root") or [])
    return deny_names, include_root


def _existing_row_line(portable_text: str, row_name: str) -> Tuple[int, str]:
    lines = portable_text.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if line.startswith(f"{row_name}|"):
            return idx, line
    raise GeneratorError(f"{_PORTABLE_PATH} declares no '{row_name}' row")


def _existing_exclusions(row_line: str) -> List[str]:
    fields = row_line.rstrip("\n").split("|")
    if len(fields) <= _ALLOWLIST_FIELD:
        raise GeneratorError(f"row line does not carry an allowlist field: {row_line!r}")
    entries = [e for e in fields[_ALLOWLIST_FIELD].split(",") if e]
    return [e for e in entries if e.startswith("!")]


def _derive_row(rows: Dict, row_name: str, source_subdir: str, portable_text: str) -> Dict:
    tracked = _tracked_top_level_names(source_subdir)
    deny_names, include_root = _row_declarations(rows, row_name)

    overlap = sorted(set(deny_names) & set(include_root))
    if overlap:
        raise GeneratorError(
            f"'{row_name}': {len(overlap)} name(s) declared in BOTH 'deny' and "
            f"'include_root' — a whole-entry deny and an admission cannot "
            f"coexist for the same name: {overlap}"
        )

    classified = set(deny_names) | set(include_root)
    unclassified = sorted(set(tracked) - classified)
    if unclassified:
        raise GeneratorError(
            f"'{row_name}': {len(unclassified)} git-tracked top-level name(s) under "
            f"'{source_subdir}' appear in NEITHER 'deny' nor 'include_root' in "
            f"{_DECLARATIONS_PATH} — unclassified, so this row cannot ship them "
            f"(deny-by-default, not opt-out): {unclassified}"
        )

    stale = sorted(classified - set(tracked))
    if stale:
        raise GeneratorError(
            f"'{row_name}': {len(stale)} name(s) declared in "
            f"{_DECLARATIONS_PATH} are no longer git-tracked under "
            f"'{source_subdir}' — the declaration is stale (renamed/removed "
            f"upstream), remove or update it: {stale}"
        )

    if row_name == "claude-klabauter":
        for contract_path, owning_root in _CONTRACT_ROOTS:
            if owning_root not in include_root:
                raise GeneratorError(
                    f"'{row_name}': AC9 contract root {contract_path!r} depends on "
                    f"directory-granular admission of {owning_root!r}, which is not "
                    f"in 'include_root' — this row can no longer carry it"
                )
            if not (_REPO_ROOT / contract_path).exists():
                raise GeneratorError(
                    f"'{row_name}': AC9 contract root {contract_path!r} is missing "
                    f"from disk — a silent drop here breaks a cross-repo consumer "
                    f"with no failing test in this repo"
                )
        missing_directory_granular = sorted(
            _DIRECTORY_GRANULAR_NAMES - set(include_root)
        )
        if missing_directory_granular:
            raise GeneratorError(
                f"'{row_name}': AC9 directory-granular name(s) not present in "
                f"'include_root' — {missing_directory_granular} must be INCLUDED "
                f"at directory granularity, not merely classified (a whole-entry "
                f"'deny' does not satisfy AC9): roughly 30 sibling-visible modules "
                f"ship today only because these entries are coarse, including "
                f"sixteen hook handlers on every session's hot path — siblings "
                f"resolve the engine root and import 'coordinator_core.*' in "
                f"their own process: {missing_directory_granular}"
            )

    idx, row_line = _existing_row_line(portable_text, row_name)
    exclusions = _existing_exclusions(row_line)
    fields = row_line.rstrip("\n").split("|")
    new_csv = ",".join(sorted(include_root) + exclusions)
    fields[_ALLOWLIST_FIELD] = new_csv
    new_line = "|".join(fields) + "\n"

    old_inclusions = sorted(
        e for e in row_line.rstrip("\n").split("|")[_ALLOWLIST_FIELD].split(",")
        if e and not e.startswith("!")
    )
    added = sorted(set(include_root) - set(old_inclusions))
    removed = sorted(set(old_inclusions) - set(include_root))

    return {
        "line_index": idx,
        "old_line": row_line,
        "new_line": new_line,
        "added": added,
        "removed": removed,
        "tracked_count": len(tracked),
        "include_count": len(include_root),
        "deny_count": len(deny_names),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 0 if generation is idempotent against the file on disk; write nothing",
    )
    args = parser.parse_args(argv)

    rows = _load_declarations()
    portable_text = _PORTABLE_PATH.read_text(encoding="utf-8")

    try:
        derivations = [
            _derive_row(rows, row_name, source_subdir, portable_text)
            for row_name, source_subdir in _ROWS
        ]
    except GeneratorError as exc:
        print(f"publish-allowlist-generate: {exc}", file=sys.stderr)
        return 1

    divergent = [d for d in derivations if d["old_line"] != d["new_line"]]

    if args.check:
        if divergent:
            for (row_name, _src), d in zip(_ROWS, derivations):
                if d["old_line"] == d["new_line"]:
                    continue
                print(f"'{row_name}' field 7 is stale:", file=sys.stderr)
                if d["added"]:
                    print(f"  + {len(d['added'])} added: {d['added']}", file=sys.stderr)
                if d["removed"]:
                    print(f"  - {len(d['removed'])} removed: {d['removed']}", file=sys.stderr)
            print(
                "Remedy: run publish-allowlist-generate.py without --check.",
                file=sys.stderr,
            )
            return 1
        print("publish-allowlist-generate --check: field 7 is current for both rows.")
        return 0

    if divergent:
        lines = portable_text.splitlines(keepends=True)
        for d in derivations:
            lines[d["line_index"]] = d["new_line"]
        _PORTABLE_PATH.write_text("".join(lines), encoding="utf-8", newline="\n")

    for (row_name, _src), d in zip(_ROWS, derivations):
        print(
            f"{row_name}: {d['include_count']} included, {d['deny_count']} denied, "
            f"{d['tracked_count']} tracked."
        )
        if d["added"]:
            print(f"  + {len(d['added'])} added: {d['added']}")
        if d["removed"]:
            print(f"  - {len(d['removed'])} removed: {d['removed']}")
        if not d["added"] and not d["removed"]:
            print("  (no change)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
