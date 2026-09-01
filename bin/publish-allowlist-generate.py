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
it reads `setup/publish-allowlist-declarations.yaml`'s `deny` list for a row
and regenerates the row's field-7 CSV as `sorted(tracked - deny)` followed by
the row's EXISTING `!`-prefixed narrow exclusions carried over verbatim (this
script never re-derives the deny-segment/fixture-tree narrows already
hand-authored on the row — see each row's own comment block in
`setup/publish-targets.portable` for those).

POLARITY — inverted 2026-09-01 by PM ruling; AC15 went with it. Admission is
`tracked - deny`, so an unclassified tracked name PUBLISHES rather than being
withheld. What that costs, what it provably did not move, and the one hazard
it creates (a new `coordinator/bin` CLI whose closure reaches a denied
package) are recorded once in
`docs/decisions/DR-the-publish-allowlist-became-a-denylist.md` — including
why a grep for `--verify-bin-deny` finds no caller when the detector is a
`cadence`-marked test calling `derive_bin_deny` directly.

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
    publish-allowlist-generate.py
        --verify-bin-deny                    exit 0 if every bin-row CLI whose
                                              coordinator_core import closure
                                              reaches an engine-row-denied
                                              package is covered by the bin
                                              row's authored `deny`; exit 1
                                              naming the offenders. Off by
                                              default — see `derive_bin_deny`'s
                                              docstring for why this walk is
                                              not on this script's hot path.
                                              Was a separate CLI
                                              (`verify-bin-deny.py`, deleted
                                              2026-09-01): cost-placement is a
                                              property of when code runs, not
                                              which file it lives in, and a
                                              flag not passed costs the same
                                              zero as a CLI not invoked.

Negative-spec:
    - Does NOT run the bin row's reachability-import closure on `--check` or
      the default (write) path. `derive_bin_deny` / `_assert_bin_deny_covers_
      derived` live here, beside the declarations they read, and are reachable
      only via `--verify-bin-deny`, off by default — see `derive_bin_deny`'s
      docstring for why the ~3.1s walk is charged to the act of adding a bin
      entrypoint rather than to every run of this generator.

      The ORIGINAL negative-spec here claimed the closure need not be
      re-derived because it is "a rule that does not change between runs unless
      a human re-authors the yaml". That was true of the RULE and false of its
      OUTPUT: the output changes whenever anyone adds a `coordinator/bin` CLI,
      which is exactly when nobody re-authors the yaml. Frozen output was safe
      only because an unclassified name hard-errors under an allowlist; under
      the ratified deny-by-default inversion the same CLI would publish and
      raise ImportError on an OSS clone. So the derivation exists now — just
      not on this script's hot paths.
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


#: The bin row's rule, restated once: a top-level CLI whose `coordinator_core.*`
#: import closure reaches a package the ENGINE row denies cannot ship, because a
#: published bin CLI importing a package the mirror's engine row never carries
#: raises ImportError on an OSS clone the instant it runs. The denied set is read
#: from the engine row's own `deny` at runtime, never duplicated here — two
#: spellings of "which packages are denied" is exactly the drift this file exists
#: to remove.
_BIN_ROW_NAME = "claude-klabauter-coordinator-bin"
_BIN_SOURCE_SUBDIR = "coordinator/bin"


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


def _row_declarations(rows: Dict, row_name: str) -> List[str]:
    """The row's `deny` list — the ONLY membership declaration a row carries.

    `include_root` was a literal enumeration of everything else (184 names on
    the engine row, 951 on the bin row) and is gone: it is now DERIVED as
    `tracked - deny` by `_derive_row`. See this module's docstring for the
    ruling and why the enumeration was the thing that had to go."""
    row = rows.get(row_name)
    if row is None:
        raise GeneratorError(f"{_DECLARATIONS_PATH} declares no '{row_name}' row")
    deny_entries = row.get("deny") or []
    return sorted(
        entry["name"] if isinstance(entry, dict) else entry for entry in deny_entries
    )


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


#: Path -> parsed `ast.Module` (or `None` for an unparseable file), keyed by
#: absolute path. `_core_module_imports` is called once per file per closure
#: visit and closures overlap heavily (many bin CLIs share transitive
#: dependencies), so caching the parse — not just the derived ref set, since
#: the ref set also depends on the caller-supplied `package` argument — is
#: what removes the redundant re-`ast.parse` cost. See `derive_bin_deny`'s
#: docstring for the measured effect.
_PARSE_CACHE: Dict[Path, object] = {}


def _parse_cached(path: Path):
    import ast

    if path not in _PARSE_CACHE:
        try:
            _PARSE_CACHE[path] = ast.parse(
                path.read_text(encoding="utf-8", errors="replace"), filename=str(path)
            )
        except (SyntaxError, OSError):
            _PARSE_CACHE[path] = None
    return _PARSE_CACHE[path]


def _core_module_imports(path: Path, package: str = "") -> "set":
    """Every `coordinator_core` dotted remainder `path` imports. Deliberately
    NOT guard-aware: an import this walk skips is an edge the derivation cannot
    see, and for a deny rule the safe direction is to over-collect edges (a
    CLI wrongly denied fails to publish, recoverably) rather than under-collect
    (a CLI wrongly published is dead on import on a clone).

    `package` is `path`'s own dotted `coordinator_core` package name (the
    enclosing package for a regular module, or the package's own name for an
    `__init__.py`), used to resolve `node.level` (a relative import) to an
    absolute dotted remainder. Left empty for a file outside `coordinator_core`
    (a `coordinator/bin` entrypoint), where a relative import cannot reach
    `coordinator_core` and resolving one is meaningless.

    A relative import is NOT a lesser edge than an absolute one: `node.level`
    is nonzero for exactly `from . import x` / `from .mod import y`, and
    `coordinator_core` uses these throughout (`bash_guards`, `spawn_policy`,
    `message_register`, `ops`, and others). Dropping them was itself an
    under-collection this function's own docstring forbids."""
    tree = _parse_cached(path)
    if tree is None:
        return set()
    import ast

    refs = set()
    pkg_parts = package.split(".") if package else []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                if not pkg_parts or node.level > len(pkg_parts):
                    # Climbs above what `package` can resolve (e.g. a level-2
                    # relative import from a top-level package) -- no
                    # coordinator_core-rooted target to name; drop rather than
                    # guess.
                    continue
                base = pkg_parts[: len(pkg_parts) - node.level + 1]
                if node.module:
                    refs.add(".".join(base + node.module.split(".")))
                elif base:
                    # `from . import x[, y, ...]` -- module is None, level 1
                    # (or higher): each imported name IS a submodule/attribute
                    # of the resolved base package.
                    for alias in node.names:
                        refs.add(".".join(base + [alias.name]))
                continue
            if not node.module:
                continue
            if node.module == "coordinator_core":
                for alias in node.names:
                    refs.add(alias.name)
            elif node.module.startswith("coordinator_core."):
                refs.add(node.module[len("coordinator_core.") :])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("coordinator_core."):
                    refs.add(alias.name[len("coordinator_core.") :])
    return refs


def _module_file_and_package(mod: str) -> Tuple[object, str]:
    """The file `mod` (a dotted `coordinator_core` remainder) resolves to,
    and the dotted package name to resolve THAT file's own relative imports
    against. `(None, "")` if `mod` names no file under `coordinator_core`
    (e.g. it is an imported NAME, not a module -- `closure()`'s existing
    fallback for that case is unchanged)."""
    base = Path(*mod.split("."))
    init_candidate = _REPO_ROOT / "coordinator_core" / base / "__init__.py"
    if init_candidate.is_file():
        return init_candidate, mod
    file_candidate = (_REPO_ROOT / "coordinator_core" / base).with_suffix(".py")
    if file_candidate.is_file():
        package = mod.rsplit(".", 1)[0] if "." in mod else ""
        return file_candidate, package
    return None, ""


def _make_closure(known: "set"):
    """Build a `closure(mod) -> set` reachable-package-name function that is
    safe against import cycles in `coordinator_core` (P2,
    coordinatorcode-reviewer.a8adfc8a37d0c78b6). 59 real cycles exist in the
    current tree (`ops.fleet._common` <-> `ops.queue_append`, `ipc` <->
    `ops._registry_map`, `warm.engine_root` <-> `warm.skew`, and more) —
    reachable from bin CLIs, not merely theoretical.

    A plain memoized recursive walk (the prior implementation) writes an
    in-progress empty-set sentinel into its memo before recursing, so a back
    edge inside a cycle can read that sentinel back as if it were the
    module's COMPLETE reached-set — silently under-collecting for whichever
    caller's memo entry gets finalized from the incomplete value, and because
    memoization is permanent, a later, unrelated top-level closure() call can
    reuse the same wrong cached value. This is Tarjan's strongly-connected-
    components algorithm instead: every module in a cycle is grouped into one
    SCC, the SCC's reached-set is computed as the union of ALL its members'
    direct edges plus every already-known(*) external SCC's reached-set, and
    `closure(mod)` returns that SCC's set — correct regardless of which
    member of the cycle is entered first or which edge order `ast.walk`
    returns.

    (*) "already-known" is Tarjan's own guarantee: children are always fully
    resolved (finalized SCC, or still-open and folded into the same SCC as
    this frame) before a parent's SCC closes."""
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Dict[str, bool] = {}
    stack: List[str] = []
    counter = [0]
    scc_reached: Dict[int, "set"] = {}
    mod_scc: Dict[str, int] = {}
    next_scc_id = [0]

    def refs_of(mod: str) -> "set":
        path, package = _module_file_and_package(mod)
        if path is None:
            return set()
        return _core_module_imports(path, package)

    def target_of(ref: str):
        if ref in known:
            return ref
        top = ref.split(".", 1)[0]
        return top if top in known else None

    def strongconnect(mod: str) -> None:
        indices[mod] = counter[0]
        lowlink[mod] = counter[0]
        counter[0] += 1
        stack.append(mod)
        on_stack[mod] = True

        for ref in refs_of(mod):
            target = target_of(ref)
            if target is None:
                continue
            if target not in indices:
                strongconnect(target)
                lowlink[mod] = min(lowlink[mod], lowlink[target])
            elif on_stack.get(target):
                lowlink[mod] = min(lowlink[mod], indices[target])

        if lowlink[mod] != indices[mod]:
            return

        scc_id = next_scc_id[0]
        next_scc_id[0] += 1
        component = []
        while True:
            w = stack.pop()
            on_stack[w] = False
            component.append(w)
            mod_scc[w] = scc_id
            if w == mod:
                break

        reached: "set" = set()
        for member in component:
            reached.add(member.split(".", 1)[0])
            for ref in refs_of(member):
                target = target_of(ref)
                if target is None:
                    reached.add(ref.split(".", 1)[0])
                elif target not in component:
                    reached |= scc_reached[mod_scc[target]]
        scc_reached[scc_id] = reached

    def closure(mod: str) -> "set":
        if mod not in mod_scc:
            strongconnect(mod)
        return scc_reached[mod_scc[mod]]

    return closure


def derive_bin_deny(rows: Dict) -> List[str]:
    """Derive the MECHANICAL half of the bin row's `deny` list.

    Returns the sorted names: the tracked `.py`/`.cmd`/
    `.ps1` members of every top-level bin CLI whose `coordinator_core` import
    closure reaches a package the engine row denies.

    This is the walk `setup/publish-allowlist-declarations.yaml` records as
    having been run once by hand on 2026-08-20 and frozen ever since. Frozen was
    safe under an allowlist — a later CLI reaching a denied package is
    unclassified, so this generator refuses and it cannot ship. It is NOT safe
    under deny-by-default, where the same CLI would publish and then ImportError
    on an OSS clone. Deriving it here is the precondition for that inversion.

    Measured 2026-09-01 (pre relative-import/cycle fix): ~3.1s own-CPU, 431
    top-level bin `.py` files, 883 modules parsed, 2 `git ls-files` spawns.
    Re-measured after coordinatorcode-reviewer.a8adfc8a37d0c78b6's P1
    (relative imports were silently dropped -- see `_core_module_imports`)
    and P2 (`closure()` memoization was not cycle-safe against the 59 real
    import cycles in this tree -- see `_make_closure`) fixes: ~3.6-3.8s
    own-CPU, 886 files parsed, same 20 derived names (the new edges reach no
    additional denied package on the CURRENT tree). Parsing is now cached by
    path (`_PARSE_CACHE`) rather than re-`ast.parse`d per visit -- measured
    to have negligible effect here (886 unique files parsed either way; the
    prior memoization already prevented most redundant closure() re-entry,
    so there was little redundant parsing to cache away). The added edges
    from following relative imports, not the parse, are what cost the extra
    ~0.5-0.7s. Paid only when `--verify-bin-deny` is passed — off this
    script's hot path (moved off `--check` at 05e05143fd after landing at
    2812ms there), since the set only changes when a `coordinator/bin`
    entrypoint is added.

    A content fingerprint over exactly these inputs was built to skip the walk
    and then DELETED, measured rather than reasoned: this repo's shared branch
    took 44 commits in one hour, 3 of them touching `coordinator_core` or
    `coordinator/bin` within 20 minutes, so the fingerprint missed essentially
    always and the cache bought nothing while adding a sidecar, a schema, and a
    second artifact that could itself go stale. Do not re-add one without first
    measuring the hit rate on a live shared branch — "it costs 0ms when it hits"
    is not the question; how often it hits is."""
    denied_packages = {
        (entry["name"] if isinstance(entry, dict) else entry).removesuffix(".py")
        for entry in (rows["claude-klabauter"].get("deny") or [])
    }

    core_files = _git_ls_files("coordinator_core")
    bin_files = _git_ls_files(_BIN_SOURCE_SUBDIR)

    known: "set" = set()
    for rel in core_files:
        parts = Path(rel).parts[1:]
        if not parts:
            continue
        if parts[-1].endswith(".py"):
            stem = parts[:-1] + (parts[-1][:-3],)
            known.add(".".join(stem))
            if stem[-1] == "__init__":
                known.add(".".join(stem[:-1]))
        for i in range(1, len(parts)):
            known.add(".".join(parts[:i]))

    top_level = sorted(
        p for p in bin_files if len(Path(p).parts) == 3 and p.endswith(".py")
    )
    tracked_names = {Path(p).parts[2] for p in bin_files if len(Path(p).parts) == 3}

    closure = _make_closure(known)

    derived: "set" = set()
    for rel in top_level:
        reached: "set" = set()
        for ref in _core_module_imports(_REPO_ROOT / rel):
            reached |= closure(ref)
        if reached & denied_packages:
            stem = Path(rel).parts[2][:-3]
            derived |= {
                n
                for n in (f"{stem}.py", f"{stem}.cmd", f"{stem}.ps1")
                if n in tracked_names
            }

    return sorted(derived)


def _assert_bin_deny_covers_derived(rows: Dict) -> List[str]:
    """Assert every mechanically-derived bin deny name is present in the bin
    row's hand-authored `deny`. Returns the derived names.

    This is the AUTHORING-TIME half of the fix: the walk (cost recorded once,
    on `derive_bin_deny`) runs only under `--verify-bin-deny`, the act that
    can change the answer — adding a `coordinator/bin` entrypoint.

    It VERIFIES rather than REPLACES the authored list, deliberately. That list
    is a SUPERSET: 20 of its 32 entries are mechanical, and 12 are edges no AST
    walk can see (`coordinator-publish.py`'s `runpy.run_path`,
    `percolate-push.py`'s shell-out to `percolate-gate.py`) or conventions
    (`.percolate-ignore`, the top-level prose tests). Replacing the list with
    the derivation would silently drop those twelve — which is why the polarity
    inversion, when it lands, must keep a declared half rather than deriving
    everything.

    What it catches that nothing catches today: a NEW CLI whose closure reaches
    a denied package and that nobody noticed. Today that ships and raises
    ImportError on the first OSS clone to run it."""
    # No-op when the real rows are absent. `_ROWS`/`_DECLARATIONS_PATH` are
    # module-level constants the test harness monkeypatches to point at a
    # throwaway fixture repo (see coordinator/tests/
    # test_publish_allowlist_generate.py's header), and a fixture declares
    # neither production row. NOT a fail-open: both rows are present in the
    # real declarations file, and their absence there hard-errors in
    # `_row_declarations` before reaching here.
    if _BIN_ROW_NAME not in rows or "claude-klabauter" not in rows:
        return []

    derived = derive_bin_deny(rows)
    authored = set(rows[_BIN_ROW_NAME].get("deny") or [])
    missing = sorted(set(derived) - authored)
    if missing:
        raise GeneratorError(
            f"'{_BIN_ROW_NAME}': {len(missing)} name(s) whose coordinator_core "
            f"import closure reaches an engine-row-denied package are NOT in this "
            f"row's 'deny' — publishing them ships a CLI that raises ImportError "
            f"on a fresh clone the instant it runs: {missing}"
        )
    return derived


def _derive_row(rows: Dict, row_name: str, source_subdir: str, portable_text: str) -> Dict:
    tracked = _tracked_top_level_names(source_subdir)
    deny_names = _row_declarations(rows, row_name)

    # THE INVERSION (PM ruling, 2026-09-01). Admission is `tracked - deny`, not
    # an enumerated `include_root`. An unclassified name no longer hard-errors;
    # it publishes. See the module docstring for the ruling and its cost.
    include_root = sorted(set(tracked) - set(deny_names))

    stale = sorted(set(deny_names) - set(tracked))
    if stale:
        raise GeneratorError(
            f"'{row_name}': {len(stale)} name(s) in 'deny' are no longer "
            f"git-tracked under '{source_subdir}' — the declaration is stale "
            f"(renamed/removed upstream), remove or update it: {stale}"
        )

    if row_name == "claude-klabauter":
        for contract_path, owning_root in _CONTRACT_ROOTS:
            # Restated for the inverted polarity: under an enumeration this
            # asked "is the parent admitted?"; now admission is the default, so
            # the only way to lose the parent is to DENY it. Same guarantee,
            # opposite question.
            if owning_root in deny_names:
                raise GeneratorError(
                    f"'{row_name}': AC9 contract root {contract_path!r} depends on "
                    f"directory-granular admission of {owning_root!r}, which is in "
                    f"'deny' — this row can no longer carry it"
                )
            if owning_root not in tracked:
                raise GeneratorError(
                    f"'{row_name}': AC9 contract root {contract_path!r} depends on "
                    f"{owning_root!r}, which is not git-tracked under "
                    f"'{source_subdir}' — nothing admits it and this row cannot "
                    f"carry it"
                )
            if not (_REPO_ROOT / contract_path).exists():
                raise GeneratorError(
                    f"'{row_name}': AC9 contract root {contract_path!r} is missing "
                    f"from disk — a silent drop here breaks a cross-repo consumer "
                    f"with no failing test in this repo"
                )
        denied_directory_granular = sorted(
            _DIRECTORY_GRANULAR_NAMES & set(deny_names)
        )
        untracked_directory_granular = sorted(_DIRECTORY_GRANULAR_NAMES - set(tracked))
        if denied_directory_granular or untracked_directory_granular:
            lost = sorted(set(denied_directory_granular) | set(untracked_directory_granular))
            raise GeneratorError(
                f"'{row_name}': AC9 directory-granular name(s) would not ship — "
                f"{lost} must be INCLUDED at directory granularity: roughly 30 "
                f"sibling-visible modules ship today only because these entries "
                f"are coarse, including sixteen hook handlers on every session's "
                f"hot path — siblings resolve the engine root and import "
                f"'coordinator_core.*' in their own process: {lost}"
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
    parser.add_argument(
        "--verify-bin-deny",
        action="store_true",
        help=(
            "exit 0 if every derived bin-row deny name is present in the "
            "authored 'deny' list; exit 1 naming the offenders. Asserts "
            "nothing about field 7, writes nothing."
        ),
    )
    args = parser.parse_args(argv)

    if args.verify_bin_deny:
        rows = _load_declarations()
        try:
            derived = _assert_bin_deny_covers_derived(rows)
        except GeneratorError as exc:
            print(f"publish-allowlist-generate --verify-bin-deny: {exc}", file=sys.stderr)
            print(
                "  Remedy: add the named entries to "
                "setup/publish-allowlist-declarations.yaml's "
                "'claude-klabauter-coordinator-bin.deny' list, with the rationale "
                "at the point of enforcement.",
                file=sys.stderr,
            )
            print(
                "  Two sibling legs of the same complement, NOT checked here — run "
                "them too when adding a bin entrypoint:\n"
                "    forwarder parity:  pytest coordinator_core/test_bin_launcher_parity.py\n"
                "    classification:    coordinator/bin/publish-allowlist-generate.py --check",
                file=sys.stderr,
            )
            return 1
        print(
            f"publish-allowlist-generate --verify-bin-deny: {len(derived)} derived "
            f"name(s), all present in the bin row's deny list."
        )
        return 0

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
