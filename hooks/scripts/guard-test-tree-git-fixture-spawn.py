"""PreToolUse hook (matcher: Write|Edit|MultiEdit|NotebookEdit, via
`preuse-write-dispatch.py` -> `_guard_runner.REAL_GUARD_REGISTRY`):
write-time ADVISORY that fires when a proposed test-tree edit shells `git`
to construct fixture state.

C9, `docs/plans/2026-08-07-restore-the-excised-tests-spawn-free.md`. Re-
pointed 2026-08-07 by PM correction from a hard DENY to an OFFER -- the
plan's own words: *"I never said 'no git'. I said I wanted to end the
spawning and deterioration."* This is an ADVISORY (`CHANNEL_ADDITIONAL_
CONTEXT`), never a deny -- it never blocks the edit, and it leads with the
alternative (a fake-git fixture module, resolved on disk per-repo by
`_resolve_anchor`) rather than a prohibition,
per this repo's "offers, not nags" default and the same message-format
precedent `nudge-plan-test-surface-tier.py` and `guard-doctrine-changelog-
prose.py` already use ("name the offender, then say what to do instead").

WHAT FIRES -- fixture-construction git call sites only, matching AC2's
amended scope (see the plan's AC2 correction: "zero git-spawning fixture-
construction call sites under coordinator/tests", not "zero git call sites
of any shape"). A `git` argv0 whose SUBCOMMAND is one of
`_FIXTURE_CONSTRUCTION_SUBCOMMANDS` (state-building: `init`, `config`,
`add`, `commit`, `worktree`, `clone`, `checkout`, `reset`, `branch`, `tag`,
`remote`, `mv`, `rm`, `stash`, `merge`, `rebase`, `cherry-pick`, `push`,
`pull`, `apply`) fires. A READ-ONLY subcommand (`show`, `log`, `rev-parse`,
`ls-files`, `diff`, `status`, `cat-file`, `blame`, `describe`, `ls-remote`,
`reflog`, `shortlog`, `name-rev`) -- e.g. C2b's `_git_history.py` -- never
fires; per the plan's AC2/AC10 amendment, a read-only git spawn is an
ordinary spawn counted by AC1's aggregate budget, not this guard's concern.
A subcommand this hook cannot statically resolve (a variable, an f-string,
a `**`-unpacked list) is treated the SAME as read-only -- fails toward NOT
advising, consistent with an offer rather than a deny: an unresolvable
shape is not confidently fixture-construction-shaped, and a guard that
nags on every uncertain case gets disabled by the first person it annoys
(the exact failure mode `guard-doctrine-surface-bash-write.py`'s own
module docstring names for a Bash-surface guard; the same reasoning
applies here for a write-time advisory).

SURFACING -- only the FIRST fixture-construction hit in a proposed edit is
surfaced per invocation (`hits[0]`); an edit with several such sites gets
one advisory, not one per site. Defensible for an offer, not exhaustive by
design -- the suite-level census (`coordinator/tests/_spawn_budget.py`) is
the backstop that reports every site.

DETECTION -- reuses `coordinator/lib/spawn_detect.py` (vendored byte-
verbatim from the sibling engine repo; imported here, never edited -- a
peer session is mid-work there) for two things ONLY: `sites_in_source()` to
find every spawn call site and its resolved argv0 (so this hook inherits
that module's handling of aliased imports, module-level constants, local
helpers, `functools.partial`, f-string prefixes, etc. for free, rather
than re-deriving a second, subtly-different notion of "is this a spawn"),
and `is_test_tree_site()` for the test-tree scope predicate (see below).
`spawn_detect.SpawnSite` carries argv0 only, never the full argv list --
so this hook does its OWN second, narrow AST pass (`_git_subcommand_at`)
to read the SECOND element of the same call's argv-bearing list literal,
joined back to the `SpawnSite` by `lineno` (the same in-memory-join idiom
`coordinator/tests/guards/test_no_bare_python_spawn.py`'s own module
docstring documents for a structurally identical need -- SpawnSite's own
docstring is explicit that it "reports CALL-SITES, never live costs" and
carries no argv beyond argv0 by design, so a second in-scope pass is the
sanctioned way to recover the subcommand, not a workaround for a gap).

SCOPE-EXPRESSION NOTE (staff-eng finding 7, minor -- amended AC10/C9 body
cites this verbatim): this hook does NOT hard-code `coordinator/tests/**`
as a literal path-prefix predicate, which the plan's own correction notes
would be inert in a consuming repo's shipped `templates/`/`guards/` copy
(no `coordinator/tests/` path exists there at all). Instead it calls
`spawn_detect.is_test_tree_site(normalized_path)` -- the SAME shared,
already-computed, structural test-tree predicate `coordinator/lib/
spawn_detect.py`'s own docstring calls "the single shared definition ...
re-deriving traversal or classification logic instead of importing [it]
is exactly how the census and the gate drifted apart twice before". That
predicate is purely structural (a `tests/` directory component anywhere,
or a `test_*` basename) -- it carries NO hardcoded `coordinator/tests/`
literal to begin with, so it is identically correct in this repo and in
any consuming repo's own test tree, with zero per-repo onboarding edit
required. The OFFER's anchor is held to the same standard by
`_resolve_anchor`: probed on disk in the edited file's own tree, dropped
entirely where no local fixture exists, never emitted as an
authoring-repo literal that dangles in a sibling. The `_guard_runner.REAL_GUARD_REGISTRY` scope descriptor that
gates whether this guard's body module is even IMPORTED (below, in
`_guard_runner.py`) is a cheap, deliberately OVER-approximating pre-filter
(`path_suffixes={".py"}`, `directory_substrings=("tests/",)` -- a bare
substring, not a `coordinator/`-anchored one, so it likewise carries no
repo-specific literal) -- the real, precise scope decision is this
module's own `is_test_tree_site()` call, exactly the two-layer shape
`_guard_runner_contract.py` clause 12 documents for every other enrolled
guard ("a descriptor's only job is to rule out payloads that could never
possibly match, cheaply, before paying an import").

BOUNDARY NOTE -- unchanged from the plan's "still load-bearing" framing:
scoped to the test tree only. Production code legitimately shells to git
(the cross-repo-memo CLI, `scoped_git_commit`, the SessionEnd hook) --
none of those live under a `tests/` directory component or carry a
`test_*` basename, so `is_test_tree_site()` never matches them; widening
this hook's scope beyond the test tree would break them, which is why the
scope check is the FIRST gate, before any spawn detection runs at all.

Contract (`_guard_runner_contract.py`): `main() -> int`, no process-level
hard exit, no `atexit`, no cwd/sys.path mutation, no cross-invocation module-global
state, import side-effect free -- mirrors every sibling enrolled guard in
this directory (`nudge-plan-test-surface-tier.py`, `guard-doctrine-
changelog-prose.py`). Fail-open at every uncertain step: unreadable/
unparseable stdin; `tool_name` not in {Write, Edit, MultiEdit}; no target
path; target not test-tree-shaped; `after`-content reconstruction
ambiguous; `spawn_detect` unimportable; `sites_in_source` raising a
`SpawnParseError` (an unparseable proposed edit is not this hook's
business to diagnose); zero fixture-construction git sites found.

Spec backlink: docs/plans/2026-08-07-restore-the-excised-tests-spawn-free.md § C9
Tripwire token: TEST-TREE-GIT-FIXTURE-SPAWN (registered in
coordinator/docs/wiki/coordinator-tripwires.md in the same commit).
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

#: coordinator/lib/ holds spawn_detect.py -- .../scripts -> hooks -> coordinator -> lib
_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from _sentinel_write_guard import extract_target_path, reconstruct_after  # noqa: E402
from _message_envelope import CHANNEL_ADDITIONAL_CONTEXT, Message, compose, emit  # noqa: E402

_GUARDED_TOOLS = ("Write", "Edit", "MultiEdit")

#: git subcommands that BUILD fixture/repository state -- see module
#: docstring "WHAT FIRES". Deliberately an allow-list, not a deny-list: an
#: unrecognised subcommand does not fire (fails toward not-advising), the
#: same conservative posture the module docstring states for an
#: unresolvable subcommand.
_FIXTURE_CONSTRUCTION_SUBCOMMANDS = frozenset(
    {
        "init",
        "config",
        "add",
        "commit",
        "worktree",
        "clone",
        "checkout",
        "reset",
        "branch",
        "tag",
        "remote",
        "mv",
        "rm",
        "stash",
        "merge",
        "rebase",
        "cherry-pick",
        "push",
        "pull",
        "apply",
    }
)

#: git subcommands that never fire this hook -- read-only history/inspection
#: queries. Not consulted for the fire decision (the allow-list above
#: already excludes them by omission); named here only so the module
#: docstring's claim ("a read-only verb never fires") is something a reader
#: can verify against a concrete set, and so a future subcommand added to
#: `_FIXTURE_CONSTRUCTION_SUBCOMMANDS` cannot silently also appear here.
_READ_ONLY_SUBCOMMANDS = frozenset(
    {
        "show",
        "log",
        "rev-parse",
        "ls-files",
        "diff",
        "status",
        "cat-file",
        "blame",
        "describe",
        "ls-remote",
        "reflog",
        "shortlog",
        "name-rev",
    }
)

assert not (_FIXTURE_CONSTRUCTION_SUBCOMMANDS & _READ_ONLY_SUBCOMMANDS)

#: Basename of the fake-git fixture module, probed for on disk in the tree
#: being edited -- never rendered as a literal. See `_resolve_anchor`.
_ANCHOR_BASENAME = "_fake_git.py"

#: This repo's own location for it, probed (not asserted) as the fallback
#: when the edited file's own test tree carries no sibling copy.
_ANCHOR_CANONICAL_RELPATH = "coordinator/tests/_fake_git.py"

_TOKEN = "TEST-TREE-GIT-FIXTURE-SPAWN"

_GIT_ARGV0 = frozenset({"git", "git.exe"})


def _index_calls_by_lineno(tree: ast.AST) -> "dict[int, list[ast.Call]]":
    """Every `ast.Call` node in `tree`, keyed by `lineno` -- the join key
    back to a `spawn_detect.SpawnSite`. See module docstring "DETECTION"."""
    index: "dict[int, list[ast.Call]]" = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            index.setdefault(node.lineno, []).append(node)
    return index


def _const_str(node: "ast.AST | None") -> "Optional[str]":
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


#: `git` global flags that can precede the subcommand token -- see
#: `_git_subcommand_at`. Flags in this set that take a separate argument
#: (`-C`, `--git-dir`, `--work-tree`, `-c`) consume the following element
#: too, so the walk skips two elements for those, one for a bare flag.
_GIT_GLOBAL_FLAGS_WITH_ARG = frozenset({"-C", "--git-dir", "--work-tree", "-c"})


def _git_subcommand_at(lineno: int, calls_by_lineno: "dict[int, list[ast.Call]]") -> "Optional[str]":
    """The literal SUBCOMMAND element of the argv-bearing list/tuple literal
    of a `subprocess.*`-shaped call at `lineno`, if statically resolvable --
    `None` for a dynamic argv (a variable, an f-string, a `**` splat, no
    resolvable subcommand element) -- see module docstring "WHAT FIRES" for
    why an unresolvable subcommand does not fire this hook. Walks `elts[1:]`
    (elts[0] is the `git`/`git.exe` argv0 itself), skipping recognised
    global flags and their arguments (`-C`, `--git-dir`, `--work-tree`,
    `-c`) so `['git', '-C', tmpdir, 'init']` still resolves to `init`
    instead of misreading `-C` as the subcommand -- a common test-fixture
    idiom this hook must not silently miss. Falls through to `None`
    (unresolvable, fails toward not-advising) if the walk runs out of
    elements before finding a non-flag token, or the first non-flag token
    is not a string constant. Deliberately checks EVERY call at this
    lineno (a line can carry more than one call site, e.g. a spawn nested
    inside another expression) and returns the first resolvable
    subcommand found."""
    for call in calls_by_lineno.get(lineno, ()):
        if not call.args:
            continue
        argv_node = call.args[0]
        if not isinstance(argv_node, (ast.List, ast.Tuple)):
            continue
        elts = argv_node.elts
        if len(elts) < 2:
            continue
        i = 1
        subcommand: "Optional[str]" = None
        while i < len(elts):
            token = _const_str(elts[i])
            if token is None:
                # Non-constant element before a subcommand is found --
                # unresolvable for this element position.
                break
            if token in _GIT_GLOBAL_FLAGS_WITH_ARG:
                i += 2
                continue
            if token.startswith("-"):
                i += 1
                continue
            subcommand = token
            break
        if subcommand:
            return subcommand
    return None


def _fixture_construction_sites(text: str, relpath: str) -> "list[tuple[str, int]]":
    """`[(subcommand, lineno), ...]` for every fixture-construction git
    call site in `text`. Empty (never raises) on any parse failure -- an
    unparseable proposed edit is not this hook's business (see module
    docstring's fail-open list)."""
    try:
        import spawn_detect  # noqa: E402  (deferred: only needed once in-scope)
    except Exception:
        return []

    try:
        sites = spawn_detect.sites_in_source(text, relpath)
    except Exception:
        return []

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    calls_by_lineno = _index_calls_by_lineno(tree)

    hits: "list[tuple[str, int]]" = []
    for site in sites:
        if site.argv0 not in _GIT_ARGV0:
            continue
        subcommand = _git_subcommand_at(site.lineno, calls_by_lineno)
        if subcommand in _FIXTURE_CONSTRUCTION_SUBCOMMANDS:
            hits.append((subcommand, site.lineno))
    return hits


def _resolve_offer_paths(target_raw: str) -> "tuple[str, Optional[str]]":
    """Both paths the offer renders, resolved against the tree the edited
    file lives in: the target as the reader's own repo-relative path, and
    the fake-git fixture anchor -- `None` for the anchor when that tree
    registers no local equivalent.

    Negative spec: never renders a path this guard has not seen on disk.
    The guard is enrolled fleet-wide and fires in every repo that installs
    it, so a hardcoded authoring-repo literal points a sibling's agent at a
    file that is not there -- an offer whose alternative does not exist is
    worse than an offer with no "See" line, which is what `None` produces.

    Probe order for the anchor: the edited file's own ancestor chain up to
    its repo root (a sibling `_fake_git.py` in the same test tree), then
    this repo's canonical location under that same root. Both are existence
    probes; a repo whose equivalent lives elsewhere gets no anchor rather
    than a wrong one. Fail-open (raw target, no anchor) on any filesystem
    error.
    """
    try:
        resolved = Path(target_raw).resolve()
        start = resolved.parent
        chain = (start, *start.parents)
        root = next((d for d in chain if (d / ".git").exists()), None)
    except Exception:
        return target_raw, None

    return _display_path(resolved, root), _resolve_anchor(chain, root)


def _resolve_anchor(chain: "tuple[Path, ...]", root: "Optional[Path]") -> "Optional[str]":
    """The anchor half of `_resolve_offer_paths` -- see its docstring for
    the probe order and why a miss returns `None` rather than a literal."""
    try:
        for directory in chain:
            candidate = directory / _ANCHOR_BASENAME
            if candidate.is_file():
                return _display_path(candidate, root)
            if directory == root:
                break

        if root is not None:
            canonical = root / _ANCHOR_CANONICAL_RELPATH
            if canonical.is_file():
                return _display_path(canonical, root)
    except Exception:
        return None

    return None


def _display_path(path: Path, root: "Optional[Path]") -> str:
    if root is not None:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _advisory_message(
    target: str, subcommand: str, lineno: int, anchor: "Optional[str]"
) -> Message:
    alternative = (
        f"{anchor} builds the same state as plain files"
        if anchor
        else "plain files build the same state"
    )
    return compose(
        f"{_TOKEN}: {target}:{lineno} shells \"git {subcommand}\" to build "
        f"test fixture state -- {alternative}, no spawn; unless real git's "
        "behaviour is the assertion.",
        anchor=anchor,
    )


def main() -> int:
    try:
        return _main_impl()
    except Exception:
        return 0


def _main_impl() -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    if not raw:
        return 0

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
    except Exception:
        return 0

    if payload.get("tool_name", "") not in _GUARDED_TOOLS:
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0

    target_raw = extract_target_path(tool_input)
    if not target_raw:
        return 0

    try:
        import spawn_detect  # noqa: E402
    except Exception:
        return 0

    normalized = target_raw.replace(os.sep, "/")
    if not spawn_detect.is_test_tree_site(normalized):
        return 0

    try:
        target_path = Path(target_raw)
        before = (
            target_path.read_text(encoding="utf-8", errors="replace")
            if target_path.is_file()
            else ""
        )
    except Exception:
        before = ""

    after = reconstruct_after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return 0

    hits = _fixture_construction_sites(after, normalized)
    if not hits:
        return 0

    subcommand, lineno = hits[0]
    display_target, anchor = _resolve_offer_paths(target_raw)
    emit(
        _advisory_message(display_target, subcommand, lineno, anchor),
        CHANNEL_ADDITIONAL_CONTEXT,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
