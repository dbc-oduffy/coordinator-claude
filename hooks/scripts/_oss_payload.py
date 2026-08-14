"""Single source of truth for "which tracked files actually reach the OSS
`coordinator-claude` mirror" — derived live from the ratified allowlist
(`setup/publish-targets.portable` field 7) and the ratified exclusion layer
(`coordinator/.percolate-ignore`), never a hand-maintained directory tuple.

WHY THIS MODULE EXISTS: a directory tuple copied by hand drifts from the
allowlist that actually governs publish the moment either side changes. This
module composes the two ratified layers instead, so a later ratchet/guard
that imports it tracks the allowlist automatically.

SIX target rows in `setup/publish-targets.portable` compose the actual OSS
`coordinator-claude` mirror; this module models exactly TWO of them —
`coordinator-claude|mirror` (the bulk of the payload) and
`coordinator-claude-toplevel-wiki` (a small, separately-allowlisted set of
seed wiki pages) — because those are the only two rows a local ratchet/guard
needs to reason about tracked source paths for. The other four rows
(`coordinator-claude-toplevel-install`, the two `dist/`-sourced flat-mirror
rows, and the disabled `setup`-sourcing row) publish generated/curated
install surfaces this module has no reason to enumerate.

COMPOSITION, in order:
  1. Field 7 of the `coordinator-claude|mirror` row names the admitted
     top-level entries (`bin`, `lib`, `hooks`, `skills`, ..., specific
     `docs/wiki/*.md` seed pages, specific `templates/*` paths, ...).
  2. Field 8 (`source_map`) reroutes SOME of those entries (today: `bin`,
     `lib`) to resolve against a SIBLING repo's tree (`claude-klabauter`)
     instead of this repo's — those two directories are tracked as 0 files
     in this clone BY DESIGN (the executable surface migrated out on
     2026-07-22); resolving them here would silently under-count by roughly
     two thirds of the real payload (bin: 342 files, lib: 61, against this
     repo's own hooks/: 85, measured 2026-07-21).
  3. `coordinator/.percolate-ignore` then excludes specific subtrees INSIDE
     admitted entries — `bin/tests/`, `hooks/scripts/tests/`, `lib/tests/`,
     `snippets/registry.toml`, and two agent files, among others. The
     allowlist alone overstates the shipping set; only the composition of
     both layers is accurate.
  4. `.percolate-ignore` ALSO carries a blanket `docs/` directory-exclude
     pattern. This is INTENTIONAL, not a defect: it exists so the
     `coordinator-claude|mirror` row's wholesale copy never collides with
     the dedicated `coordinator-claude-toplevel-wiki` flat-mirror row, which
     is the row that actually ships the curated `docs/wiki/*.md` seed pages
     admitted by name in field 7. Those pages are therefore individually
     admitted to field 7 (so a fail-loud allowlist-vs-tracked check never
     flags them absent) AND wholesale-excluded from the mirror row's own
     copy (so the two rows never double-write the same destination path) —
     both true at once by design. `local_payload_files()` (the mirror row
     leg) correctly omits them; `toplevel_wiki_payload_files()` (the
     dedicated-row leg) is where they are actually enumerated. Reading the
     mirror-row omission alone as an under-count is the exact misdiagnosis
     this note exists to prevent — check the composed `payload_files()`,
     which includes both legs, before concluding a seed page is missing.

ENUMERATION IS `git ls-files`, NEVER a filesystem walk. A tree walk picks up
untracked build artifacts (`__pycache__/*.pyc` compiled from this machine,
embedding this machine's absolute paths in their docstrings) that a fresh
clone or a different machine will never have — measured gap: a walk over
`coordinator/hooks/scripts/` reported 696 hits against a tracked figure of
563. `git ls-files` is also how the exclusion layer's own semantics are
defined (SOURCE_DIR-relative patterns matched against tracked paths), so
walking would silently diverge from what the publish pipeline itself sees.

THE PERMANENT COVERAGE ASYMMETRY (state this to every future reader — an
unstated asymmetry reads as coverage a mechanism does not have): the RATCHET
TEST built on `payload_files()` watches close to the full payload, because it
can resolve the sibling engine repo and enumerate it too. A WRITE-TIME GUARD
built on `is_in_payload_path()` watches only the local third (`hooks/`,
`skills/`, `agents/`, `commands/`, ...) — a write to `bin/` or `lib/` happens
in the engine repo's own working tree, in another session, where this
repo's hook is never invoked. That gap is real and permanent, not a bug to
"fix" by trying to reach into a sibling tree's write path from here.

FAIL-LOUD vs FAIL-OPEN, and the line between them:
  - The ENGINE LEG (claude-klabauter) fails OPEN — skips cleanly and reports
    why — when the sibling repo itself can't be resolved (fresh clone, OSS
    install, a machine with no sibling checkout). A ratchet that cannot go
    green without a sibling checkout is a ratchet the next frustrated
    session deletes.
  - EVERYTHING ELSE fails LOUD: an allowlist entry that is neither
    source_map-routed NOR present via `git ls-files` in its resolved root
    raises. A silently-empty scope is exactly how a gate reports green while
    covering nothing — the same defect class as the coverage asymmetry
    above, just in the other direction.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from _engine_root import resolve_claude_klabauter_root
from _win_portability import no_console_creationflags

REPO_ROOT = Path(__file__).resolve().parents[3]

_PUBLISH_TARGETS_PATH = REPO_ROOT / "setup" / "publish-targets.portable"
_PERCOLATE_IGNORE_PATH = REPO_ROOT / "coordinator" / ".percolate-ignore"

#: Repo-relative root this row's LOCAL (non-source_map-routed) entries resolve
#: against. Field 4 of the row (`plugin-source:coordinator-claude`) is a
#: percolate-registry token that resolves to exactly this clone's
#: `coordinator/` tree — hardcoded here rather than re-resolved through the
#: registry because this module always runs FROM that clone.
_LOCAL_COORDINATOR_ROOT = REPO_ROOT / "coordinator"

#: The one sibling repo `source_map` routes to today. A token naming any
#: other repo is an unmodeled shape (fail-loud, not fail-open — see
#: `_engine_entries_by_subpath`).
_ENGINE_REPO_NAME = "claude-klabauter"

#: The dedicated seed-wiki flat-mirror row this module also models — see the
#: module docstring's COMPOSITION point 4 for why this is a second row, not a
#: bug in the mirror row's own field 7 handling.
_TOPLEVEL_WIKI_ROW_NAME = "coordinator-claude-toplevel-wiki"
_TOPLEVEL_WIKI_ROW_MODE = "flat-mirror"


@dataclass(frozen=True)
class MirrorRow:
    """The `coordinator-claude|mirror` row's two payload-shaping fields.

    `allowlist` — every admitted top-level entry from field 7, in file order.
    `source_map` — field 8, parsed: sibling-repo source-root TOKEN (e.g.
    `"plugin-source:claude-klabauter/coordinator"`) -> the allowlist entries it
    serves (e.g. `("bin", "lib")`). Entries named in ANY `source_map` value
    resolve against the mapped sibling root, never against this clone.
    `exclusions` — field 7's `!`-prefixed entries, sigil stripped, in file
    order. See `parse_mirror_row` for why they are split out rather than
    carried in `allowlist`.
    """

    allowlist: tuple
    source_map: dict
    exclusions: tuple = ()


def _read_publish_targets_lines() -> list:
    return _PUBLISH_TARGETS_PATH.read_text(encoding="utf-8").splitlines()


def _find_row_fields(name: str, mode: str) -> list:
    """Locate one row in `setup/publish-targets.portable` by its `name` and
    `mode` fields, never a line number — every row here is a peer chunk's
    active edit target in the same tree this module reads from. Returns the
    row's pipe-split fields verbatim.

    Field layout (pipe-separated, 1-indexed, per that file's own header):
    name|mode|dest|source|dest_subdir|native_slugs|allowlist|source_map.
    """
    for line in _read_publish_targets_lines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split("|")
        if len(fields) < 7:
            continue
        if fields[0] != name or fields[1] != mode:
            continue
        return fields
    raise RuntimeError(f"no {name}|{mode} row found in {_PUBLISH_TARGETS_PATH}")


def parse_mirror_row() -> MirrorRow:
    """Parse the `coordinator-claude|mirror` row's field 7 (allowlist) and
    field 8 (source_map) out of `setup/publish-targets.portable`.

    Field 7 carries two entry kinds under one comma-separated grammar: plain
    INCLUSION entries, and `!`-prefixed EXCLUSION entries that narrow a
    subpath some inclusion entry already admitted (the engine applies them
    post-copy at the restricted tree — see the engine repo's
    `coordinator/lib/percolate/allowlist.py` § "Exclusion entries"). They are
    split into separate fields here because every caller wants exactly one of
    them: an exclusion resolves to no tracked file under
    `coordinator/<entry>`, so folding it into `allowlist` trips the
    fail-loud silently-empty-scope check in `local_payload_files()` on a row
    that is in fact correct.

    Excluded paths are deliberately absent from the payload scope this
    module computes: a `!`-narrowed file does not publish, so it contributes
    nothing to any locality budget. Honouring the sigil narrows the scope
    truthfully rather than widening what the gate tolerates.
    """
    fields = _find_row_fields("coordinator-claude", "mirror")
    raw_entries = tuple(e.strip() for e in fields[6].split(",") if e.strip())
    allowlist = tuple(e for e in raw_entries if not e.startswith("!"))
    exclusions = tuple(e[1:] for e in raw_entries if e.startswith("!"))
    source_map: dict = {}
    raw_source_map = fields[7].strip() if len(fields) >= 8 else ""
    if raw_source_map:
        for pair in raw_source_map.split(";"):
            pair = pair.strip()
            if not pair:
                continue
            if "=" not in pair:
                raise RuntimeError(
                    f"malformed source_map segment {pair!r} in "
                    f"{_PUBLISH_TARGETS_PATH} — expected "
                    "<sigil>=<csv-of-allowlist-entries>"
                )
            token, entries_csv = pair.split("=", 1)
            source_map[token.strip()] = tuple(
                e.strip() for e in entries_csv.split(",") if e.strip()
            )
    return MirrorRow(
        allowlist=allowlist, source_map=source_map, exclusions=exclusions
    )


def toplevel_wiki_allowlist() -> tuple:
    """Basenames of the seed wiki pages admitted to the dedicated
    `coordinator-claude-toplevel-wiki` flat-mirror row's own field 7 —
    parsed from the same `setup/publish-targets.portable` file
    `parse_mirror_row` reads, never a hardcoded filename list."""
    fields = _find_row_fields(_TOPLEVEL_WIKI_ROW_NAME, _TOPLEVEL_WIKI_ROW_MODE)
    return tuple(e.strip() for e in fields[6].split(",") if e.strip())


# ---------------------------------------------------------------------------
# Exclusion layer — coordinator/.percolate-ignore, data-driven, never a second
# hardcoded copy (see module docstring point 3).
# ---------------------------------------------------------------------------


def excluded_patterns() -> tuple:
    """Every non-comment, non-blank pattern line in
    `coordinator/.percolate-ignore`, in file order, verbatim."""
    if not _PERCOLATE_IGNORE_PATH.is_file():
        return ()
    patterns = []
    for line in _PERCOLATE_IGNORE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        patterns.append(stripped)
    return tuple(patterns)


def _pattern_matches(rel_posix: str, pattern: str) -> bool:
    """One `.percolate-ignore` pattern against one SOURCE_DIR-relative,
    forward-slash path — semantics per that file's own header:

      dir/   -> recursive directory match (dir/* at root OR */dir/* anywhere)
      /dir/  -> root-anchored directory match (dir/* at ROOT only)
      *.ext  -> basename glob, recursive
      path   -> exact rel_path match (no slash: basename exact/glob match)
    """
    if pattern.endswith("/"):
        anchored = pattern.startswith("/")
        dirpat = pattern.strip("/")
        prefix = r"^" if anchored else r"(^|/)"
        return re.search(prefix + re.escape(dirpat) + r"/", rel_posix) is not None
    if "/" not in pattern:
        return fnmatch.fnmatch(Path(rel_posix).name, pattern)
    return rel_posix == pattern


def _is_excluded(rel_posix: str, patterns: tuple) -> bool:
    return any(_pattern_matches(rel_posix, p) for p in patterns)


# ---------------------------------------------------------------------------
# git ls-files — the ONLY enumeration mechanism this module uses (see module
# docstring: a filesystem walk sees untracked build artifacts a tracked-only
# gate must not).
# ---------------------------------------------------------------------------


def _git_ls_files(repo_root: Path, pathspec: str) -> tuple:
    """Tracked files under `pathspec`, repo-relative to `repo_root`, as
    POSIX-style forward-slash strings. Empty tuple if the pathspec matches
    nothing tracked (including a nonexistent path) — callers decide whether
    that is fail-loud or fail-open for their case."""
    result = subprocess.run(
        ["git", "ls-files", "--", pathspec],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
        **no_console_creationflags(),
    )
    return tuple(line for line in result.stdout.splitlines() if line)


_GLOB_METACHARS = re.compile(r"[*?\[\]]")


def _git_ls_files_batch(repo_root: Path, pathspecs: tuple) -> dict:
    """`_git_ls_files` for many pathspecs in ONE `git` process, returned as
    `{pathspec: (rel_posix, ...)}` with an entry for every input pathspec
    (empty tuple where nothing tracked matched).

    Negative-spec — why attribution by prefix is sound here and would NOT be
    in general: `git ls-files` reports matched paths without saying which
    pathspec matched them, so callers must re-attribute. That is only
    unambiguous while every pathspec is a literal path with no glob
    metacharacters, which is what the mirror-row allowlist is (asserted
    below, not assumed). A globbed pathspec silently mis-attributes, so this
    helper refuses one outright rather than returning a plausible-looking
    wrong answer.

    Per-edit cost is why this exists: the callers below enumerate ~77
    allowlist pathspecs, and one `git` spawn each put a hook on the
    every-edit path at ~480ms.
    """
    globbed = tuple(p for p in pathspecs if _GLOB_METACHARS.search(p))
    if globbed:
        raise ValueError(
            f"batched git ls-files requires literal pathspecs; got globs: {globbed!r}"
        )
    if not pathspecs:
        return {}
    result = subprocess.run(
        ["git", "ls-files", "--", *pathspecs],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
        **no_console_creationflags(),
    )
    matched = [line for line in result.stdout.splitlines() if line]
    out = {p: [] for p in pathspecs}
    for rel in matched:
        for spec in pathspecs:
            if rel == spec or rel.startswith(spec + "/"):
                out[spec].append(rel)
    return {spec: tuple(rels) for spec, rels in out.items()}


def _routed_entries(source_map: dict) -> set:
    routed: set = set()
    for entries in source_map.values():
        routed.update(entries)
    return routed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def local_payload_files() -> tuple:
    """Repo-relative (to `REPO_ROOT`) tracked paths this clone contributes to
    the OSS mirror payload: every allowlist entry NOT routed by `source_map`,
    enumerated via `git ls-files` and filtered through
    `coordinator/.percolate-ignore`.

    Fail-loud: an entry that is neither `source_map`-routed nor present via
    `git ls-files` raises — a silently-empty scope is how this gate would
    report green while covering nothing.
    """
    row = parse_mirror_row()
    routed = _routed_entries(row.source_map)
    patterns = excluded_patterns()
    local_entries = tuple(e for e in row.allowlist if e not in routed)
    by_spec = _git_ls_files_batch(
        REPO_ROOT, tuple(f"coordinator/{e}" for e in local_entries)
    )
    files: list = []
    for entry in local_entries:
        pathspec = f"coordinator/{entry}"
        tracked = by_spec[pathspec]
        if not tracked:
            raise RuntimeError(
                f"allowlist entry {entry!r} is not source_map-routed and has "
                f"no tracked files under {pathspec!r} in {REPO_ROOT} — "
                "silently-empty scope, not a valid state"
            )
        for rel in tracked:
            rel_to_coordinator = rel[len("coordinator/") :]
            if _is_excluded(rel_to_coordinator, patterns):
                continue
            files.append(Path(rel))
    return tuple(files)


def toplevel_wiki_payload_files() -> tuple:
    """Repo-relative (to `REPO_ROOT`) tracked paths the dedicated
    `coordinator-claude-toplevel-wiki` flat-mirror row ships:
    `coordinator/docs/wiki/<name>.md` for every basename in
    `toplevel_wiki_allowlist()`. These pages reach the OSS mirror through
    THIS row, not through `coordinator-claude|mirror` — see the module
    docstring's COMPOSITION point 4 for why the mirror row's own blanket
    `docs/` exclusion pattern does not apply here.

    Fail-loud exactly as `local_payload_files()` is: an allowlisted basename
    with no tracked file under `coordinator/docs/wiki/` raises.
    """
    names = tuple(toplevel_wiki_allowlist())
    by_spec = _git_ls_files_batch(
        REPO_ROOT, tuple(f"coordinator/docs/wiki/{n}" for n in names)
    )
    files: list = []
    for name in names:
        pathspec = f"coordinator/docs/wiki/{name}"
        tracked = by_spec[pathspec]
        if not tracked:
            raise RuntimeError(
                f"toplevel-wiki allowlist entry {name!r} has no tracked file "
                f"under {pathspec!r} in {REPO_ROOT} — silently-empty scope, "
                "not a valid state"
            )
        for rel in tracked:
            files.append(Path(rel))
    return tuple(files)


def _parse_source_map_token(token: str) -> tuple:
    """`"plugin-source:claude-klabauter/coordinator"` -> `("claude-klabauter",
    "coordinator")`. Raises on any other shape, INCLUDING a repo name other
    than `_ENGINE_REPO_NAME` — an unmodeled `source_map` token is a
    data-shape change this module's engine leg has not been taught, not a
    resolvability question (that is what `engine_repo_available` answers)."""
    prefix = "plugin-source:"
    if not token.startswith(prefix):
        raise ValueError(f"unrecognized source_map token shape: {token!r}")
    rest = token[len(prefix) :]
    if "/" not in rest:
        raise ValueError(f"source_map token missing subpath: {token!r}")
    repo_name, subpath = rest.split("/", 1)
    if repo_name != _ENGINE_REPO_NAME:
        raise ValueError(
            f"source_map token {token!r} names repo {repo_name!r}, but this "
            f"module's engine leg only resolves {_ENGINE_REPO_NAME!r} — "
            "unmodeled source_map shape"
        )
    return repo_name, subpath


def _resolve_engine_root() -> tuple:
    """(resolved `Path` or `None`, human reason when `None`) — the single
    resolution point for the sibling engine repo. Both `engine_repo_available`
    and `engine_payload_files` route through this so the root is resolved
    once per call, not twice.

    Resolution goes through the same settings-home registry seam every other
    hook uses (`_engine_root.resolve_claude_klabauter_root` — env override, then
    `repos.claude_klabauter`, then a last-resort sibling-directory walk).
    Never raises: a fresh clone, an OSS install, or a machine without the
    sibling checkout must read as a clean skip, not a failure."""
    root = resolve_claude_klabauter_root()
    if root is None:
        return (
            None,
            "claude-klabauter repo not resolved (checked REPO_CLAUDE_KLABAUTER/"
            "CLAUDE_KLABAUTER_ROOT env, the repos.claude_klabauter registry key, and the "
            "conventional sibling-directory layout) — engine leg skipped",
        )
    path = Path(root)
    if not path.is_dir():
        return (
            None,
            f"resolved claude-klabauter path {root!r} is not a directory — "
            "engine leg skipped",
        )
    return (path, "")


def engine_repo_available() -> tuple:
    """(resolved?, human reason when not) — see `_resolve_engine_root`."""
    root, reason = _resolve_engine_root()
    return (root is not None, reason)


def engine_payload_files() -> tuple:
    """Repo-relative (to the resolved `claude-klabauter` root) tracked paths
    the ENGINE repo contributes to the OSS mirror payload, via the
    `source_map`-routed allowlist entries (today: `bin`, `lib`).

    Fail-OPEN (returns `()`) only when the engine repo itself can't be
    resolved — see `engine_repo_available`. Once resolved, fail-loud applies
    exactly as it does locally: a routed entry that is not actually present
    under its mapped subpath raises, because a broken sibling checkout
    reporting an empty-but-green engine leg is the same defect this module
    exists to prevent.
    """
    engine_root, _reason = _resolve_engine_root()
    if engine_root is None:
        return ()
    row = parse_mirror_row()
    patterns = excluded_patterns()
    token_subpaths = {
        token: _parse_source_map_token(token)[1] for token in row.source_map
    }
    pathspecs = tuple(
        f"{token_subpaths[token]}/{entry}"
        for token, entries in row.source_map.items()
        for entry in entries
    )
    by_spec = _git_ls_files_batch(engine_root, pathspecs)
    files: list = []
    for token, entries in row.source_map.items():
        subpath = token_subpaths[token]
        for entry in entries:
            pathspec = f"{subpath}/{entry}"
            tracked = by_spec[pathspec]
            if not tracked:
                raise RuntimeError(
                    f"source_map entry {entry!r} (token {token!r}) has no "
                    f"tracked files under {pathspec!r} in {engine_root} — "
                    "resolved engine repo but empty scope, not a valid state"
                )
            for rel in tracked:
                rel_to_subpath = rel[len(subpath) + 1 :]
                if _is_excluded(rel_to_subpath, patterns):
                    continue
                files.append(Path(rel))
    return tuple(files)


def payload_files() -> tuple:
    """Every tracked path that reaches the OSS mirror across the two rows
    this module models: `coordinator-claude|mirror` local entries
    (repo-relative to `REPO_ROOT`), the dedicated
    `coordinator-claude-toplevel-wiki` seed pages (also repo-relative to
    `REPO_ROOT`), and `coordinator-claude|mirror` engine entries
    (repo-relative to the resolved `claude-klabauter` root, `()` when
    unresolvable). The local and engine parts are relative to DIFFERENT repo
    roots — this is a reporting aggregate, not a single filesystem
    namespace."""
    return (
        local_payload_files()
        + toplevel_wiki_payload_files()
        + engine_payload_files()
    )


def is_payload_path(path) -> bool:
    """True if `path` (absolute, or relative to `REPO_ROOT`) names a payload
    file that lives in THIS repo — the mirror row's local entries plus the
    seed wiki pages the dedicated toplevel-wiki row ships.

    Local-only, but note precisely what that excludes and why. The engine
    third of the payload is unreachable because a write-time guard built on
    this runs in THIS repo's working tree, while a write to an
    engine-resident tree happens in the sibling repo's tree, in another
    session — see the module docstring's coverage-asymmetry note. The seed
    wiki pages are NOT in that category: they are authored here and they
    ship, so a guard can observe them and must."""
    candidate = Path(path)
    try:
        candidate = candidate.resolve()
    except Exception:
        return False
    try:
        rel = candidate.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return rel in local_payload_files() or rel in toplevel_wiki_payload_files()
