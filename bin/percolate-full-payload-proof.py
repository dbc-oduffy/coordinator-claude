"""percolate-full-payload-proof.py — proves the whole klabauter payload once,
into a wiped scratch destination, across every row, through the REAL
`publish.py` CLI entrypoint (`main()`), and proves a second publish over that
now-populated destination converges byte-identically with the first.

Why this exists: every reassuring finding count this workstream has produced
so far was measured on a narrower substrate than the real thing --
in-process against a fresh scratch destination bypassing the full gate chain
(`state/audits/2026-08-05-klabauter-scrub-and-gate-both-silent.md` § Q4), or
on two rows out of seven. This closes that gap with a repeatable artifact:
one script, one command, a verdict plus the evidence behind it, not a
"someone was careful" claim.

WHAT COUNTS AS "REAL" HERE (and what does not)
    `publish.main([])` -- the actual CLI entrypoint, unfiltered (every
    `claude-klabauter*` row, not one row via `--target`) -- is called
    IN-PROCESS (not subprocess-spawned) but otherwise completely
    unmodified: every gate `main()` itself dispatches runs for real --
    percolate-root resolution, the REAL (unedited) `percolate-store.yaml`
    and `publish-targets.portable`, identity-file presence/safety checks,
    real git-ref materialization, the real mirror-sync engine, the real content-transform
    sweep, real per-row and end-of-run guards (including all three end-of-run
    legs, `dispatch_end_of_run_identity_check`,
    `dispatch_end_of_run_install_doc_payload_check`, and
    `dispatch_end_of_run_unscanned_published_check`). The ONLY
    monkeypatch is `publish.load_targets` -- it still calls the REAL
    `percolate.targets.load_targets()` (proving every row resolves off the
    real, unedited store/portable files, real source paths, real
    native_slugs/allowlist/source_map) and then rewrites ONLY the
    `dest` field's ROOT PREFIX on each resolved row, from the real
    machine-local-resolved destination to this run's scratch destination
    (§ `_rewrite_rows_dest_root`) -- nothing about GATE, SYNC, or TRANSFORM
    behavior is touched or bypassed. This is the one deliberate, documented
    seam that makes "wiped scratch destination" possible without editing
    `setup/percolate-hooks/percolate-store.yaml` or
    `setup/publish-targets.portable` (both off-limits) or depending on
    unverified machine-local-registry env-override behavior in an
    out-of-repo installed reader (probed live and found NOT to support the
    per-key override this script would otherwise have preferred -- see
    that function's docstring).

    This means the harness is bound to the CURRENT git-committed state of
    the store/portable files at invocation time -- it is a proof of the pipeline, run
    against whatever those two carry right now, not an assertion that they
    are release-ready today.

DIRTY TREE IS NOT A GATE
    There is no dirty-tree gate in the publish path and nothing here
    overrides one. Every contributing root is materialized from its
    committed ref, so the published bytes are HEAD's whatever the working
    tree holds. `--allow-dirty-tree-override` / `--i-understand-the-risk`
    are retired no-ops, accepted only so existing invocations keep running.

TWO-PASS CONVERGENCE PROOF
    Pass 1 publishes into a freshly created (via `tempfile.mkdtemp`), truly
    EMPTY scratch destination -- the "wiped destination" the workstream's
    Next Step 5 names. Pass 2 immediately re-runs the identical `main([])`
    invocation over that now-populated destination -- no wipe, no reset,
    nothing hand-cleaned in between; this is exactly what "the second kind
    of publish, forever" means operationally. After each pass, every file
    under the scratch destination is walked and sha256-hashed by
    path-relative-to-scratch-root (§ `_hash_tree`); the verdict's
    convergence claim is `hash_tree(after pass 1) == hash_tree(after pass
    2)` -- a real byte-level comparison of the real published tree, not a
    finding-count comparison (two runs could report identical finding
    counts while differing in exactly which bytes those findings sit
    inside).

VERDICT SHAPE
    A single top-line PASS/FAIL, followed by: each pass's `publish.py` exit
    code; whether every declared `claude-klabauter*` row actually PROCESSED
    (§ ROW-COMPLETENESS below) -- a skipped row silently absent from the
    output is a HARD FAIL, never a note under a PASS; whether each end-of-run
    leg (identity check, install-doc-payload check) actually RAN, SKIPPED, or
    FAILED per pass, parsed out of that pass's captured stderr by the exact
    marker strings those two functions print
    (`dispatch_end_of_run_identity_check` /
    `dispatch_end_of_run_install_doc_payload_check` in `publish.py`) --
    never inferred from a bare exit code, because a skipped gate reading as
    clean is the precise failure class the whole workstream exists to
    close (§ that audit's own framing). A gate this script cannot find
    positive evidence of having run is reported UNKNOWN, not folded into
    a pass.

ROW-COMPLETENESS (a skipped ROW is the same failure class as a skipped LEG)
    A version-regression gate, or any other per-row
    skip inside `process_target` makes `publish.py` print "Skipping
    {name}." (or "Skipping {name} (<reason>...)") to stdout and move on --
    the run still exits 0 if every OTHER row succeeded, which is exactly how
    a real run (7 declared rows,
    2 skipped) printed a bare top-line PASS despite the largest row (the
    engine itself) never having been checked at all. `_declared_row_names`
    derives the expected `claude-klabauter*` set from `load_targets()`'s OWN
    resolved rows (never a constant this script maintains), `_parse_
    skipped_row_names` reads every "Skipping {name}" line `publish.py`
    actually printed, and `_processed_rows` independently confirms a row
    printed real sync evidence (`Synced:`/`Provenance:`) under its own `===
    name (mode) ===` header -- a row missing from BOTH the skip list and the
    processed set (silently absent from the output entirely, not merely
    unlucky wording) still fails closed via `missing_rows`. Any non-empty
    `skipped_rows`/`missing_rows` on either pass forces `overall_ok = False`
    unconditionally.

SOURCE PIN -- BOTH PASSES PUBLISH FROM THE SAME RESOLVED COMMIT SHA(S)
    A wiped scratch destination lives for the whole ~15 minute run; every
    contributing root's `git` toplevel does not -- this repo's own branch is
    a genuinely shared, actively-committed-to tree (state/audits/2026-08-05
    -blank-machine-install-readiness.md's own run: 28 peer commits landed in
    a single ~16 minute window). `publish.py`'s own `_git_materialize_ref`
    always resolves `ref="HEAD"` at the moment it is called (coordinator/bin/
    publish.py), so two `main([])` invocations separated by minutes can
    genuinely publish from two DIFFERENT commits -- a real difference in
    SOURCE, not a transform non-determinism. Reading that as a convergence
    FAILURE conflates "the fleet kept moving" with "the pipeline is not
    idempotent"; only the second is this harness's job to measure.

    Fixed here, without editing `publish.py` (constraint: this proof's own
    scope is this file and its tests): `_resolve_pinned_commit_shas` walks
    every declared row's contributing roots (`publish_module.
    parse_target_row` / `publish_module._contributing_roots`, the same
    resolution `run_pre_sync_gates` itself performs) and resolves each
    root's git toplevel and CURRENT HEAD sha exactly ONCE, before either
    pass runs -- keyed by toplevel, not by root, since `_git_materialize_ref`
    itself memoizes and archives per (toplevel, sha) and several rows
    commonly share one toplevel (this repo's five klabauter rows all do,
    today; the mechanism does not assume that stays true -- a row whose
    contributing root sits in a different repo gets its own, independently
    pinned toplevel entry). `_make_pinned_rev_parse` then wraps EACH freshly
    -imported pass module's own `_git_rev_parse` (§ `_run_one_pass`'s
    existing per-pass fresh-import discipline) so that every `("HEAD",)`
    call -- both `_git_materialize_ref`'s internal resolution, which decides
    what actually gets archived, and `run_pre_sync_gates`'s own separate
    `Provenance:` sha lookup -- answers from that one pre-resolved map
    instead of re-invoking `git rev-parse HEAD` live. A destination-side HEAD
    read (`write_lastsync_marker`'s `_git_head`, a wholly separate function)
    is never touched -- the destination legitimately differs pass 1 to pass
    2 (it is what pass 1 just wrote), and pinning it would be wrong.

    This is a SOURCE pin, not a tolerance: it does not excuse, ignore, or
    filter any byte difference `_hash_tree`/`_diff_trees` finds -- it makes
    the SOURCE bytes both passes read identical so that any difference the
    convergence check still finds is a genuine transform non-determinism,
    not fleet activity. `_parse_provenance_lines` reads `publish.py`'s own
    already-printed `Provenance: <root> shipped from <sha>` line back out of
    each pass's captured stdout as the cheapest independent verification
    that the pin actually held (both passes' provenance maps are asserted
    equal in the verdict, in addition to and independent of the byte-level
    hash comparison) -- and the verdict prints the pinned sha(s) up front,
    so a future reader never has to re-derive "was this really the same
    commit" from `git log` by hand the way this session had to.

    If a contributing root cannot be pinned at all (not a git work tree, no
    resolvable HEAD, `git` missing) `_resolve_pinned_commit_shas` raises
    `PinNotHonoredError` before either pass starts and `main` aborts loudly,
    never silently falling back to an unpinned live-HEAD read for that root.
    The same exception fires mid-run if a pass's own resolved contributing
    roots ever name a toplevel the pre-run pin walk did not cover (should
    not happen -- both walks resolve the same declared rows -- and is
    reported as exactly that discrepancy, not swallowed). A peer's commit
    landing mid-run is NOT an error case: `_make_pinned_rev_parse` detects it
    (comparing the live HEAD it can still resolve against the pin) and
    records a `head_movement_notes` entry surfaced in the verdict --
    informational, since the pin already made it moot for what got
    published, but never silently invisible either.

WHAT THIS DELIBERATELY DOES NOT COVER
    - Does not run any real publish against `$HOME/X/claude-klabauter` or
      any other live registry-resolved destination -- scratch only, by
      construction (§ `_rewrite_rows_dest_root`).
    - Does not inspect the working tree's dirtiness at all (see above) --
      publish reads a committed ref, so a dirty tree is not a finding.
    - Does not assert the published bytes are ACTUALLY clean (zero
      persona/codename leaks) -- that is what the identity-check and
      install-doc-payload end-of-run legs this script drives already
      assert; this script's own added value is proving those legs ACTUALLY
      RAN against the FULL, real, multi-row payload and that a second run
      converges, not re-implementing what they check.
    - Does not touch `setup/percolate-hooks/percolate-store.yaml` or
      `setup/publish-targets.portable` -- read-only against both.
    - Leaves no residue outside its own scratch destination: that
      directory is removed on exit unless `--keep-scratch` is passed
      (§ `main`'s `finally`).

Run: python3 coordinator/bin/percolate-full-payload-proof.py [--keep-scratch]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

_BIN_DIR = Path(__file__).resolve().parent

_TOPLEVEL_ROW_NAME = "claude-klabauter-publish-repo-toplevel"
_ROW_NAME_PREFIX = "claude-klabauter"

# `publish.py`'s "Skipping {name}." line has two printed shapes (§ grep of
# `Skipping {` across publish.py): a bare "Skipping {name}."
# (identity-file, gate failures) and "Skipping {name} (<reason>...)"
# (version-regression family). The lookahead stops at whichever terminator
# comes first so both shapes yield a clean row name, never a name plus
# trailing punctuation or a truncated reason fragment.
_SKIPPING_LINE_RE = re.compile(r"Skipping (\S+?)(?=\.|\s\()")

# The exact marker substrings `dispatch_end_of_run_identity_check` and
# `dispatch_end_of_run_install_doc_payload_check` (coordinator/bin/publish.py)
# print to stderr -- kept here as named constants, not re-derived per parse
# call, so a wording change in either function is a one-line diff to find,
# not a silent drift between what they print and what this script greps for.
_IDENTITY_RAN_CLEAN_MARKER = "end-of-run identity check"
_IDENTITY_FAIL_MARKER = "end-of-run identity check FAILED"
# Deliberately "end-of-run identity checker not found at" (§
# `dispatch_end_of_run_identity_check`'s `target_filtered=True` advisory
# WARNING), NOT the bare "identity checker not found at" substring that
# phrase contains -- that shorter substring is ALSO present in
# `dispatch_percolate_pre_ci`'s PER-ROW advisory skip WARNING (§ that
# function's docstring: a row with a non-empty `dest_subdir` can legitimately
# run, and print that exact skip warning, BEFORE its sibling toplevel row has
# published `.github/` -- the expected shape on a full, unfiltered run into a
# virgin destination, since row declaration order puts the engine row first).
# A bare substring match collided the two: on pass 1 of a virgin-destination
# publish, the per-row warning fires (and is expected to), the end-of-run leg
# runs afterward and finds `.github/` (published later in the SAME pass by
# the toplevel row) and exits clean -- printing nothing -- yet the collision
# made this parser misreport the end-of-run leg itself as `skipped-advisory`
# purely because of leftover per-row stderr chatter from earlier in the same
# pass. Traced live: `dispatch_end_of_run_identity_check` already fails
# closed unconditionally when `target_filtered=False` and the checker is
# absent (`test_full_unfiltered_run_into_virgin_destination_fails`,
# `coordinator/bin/tests/test_percolate_identity_check_gate.py`) -- the
# defect was in THIS harness's classification, not in the gate it measures.
_IDENTITY_SKIP_MARKER = "end-of-run identity checker not found at"
_INSTALL_DOC_FAIL_MARKER = "end-of-run install-doc payload check FAILED"
_INSTALL_DOC_ADVISORY_MARKER = "end-of-run install-doc payload check found"
_UNSCANNED_FAIL_MARKER = "end-of-run unscanned-published check FAILED"
_UNSCANNED_NOTE_MARKER = "DELIBERATE exclusion"


def _load_publish_module():
    """Import `coordinator/bin/publish.py` under a private module name --
    same idiom this repo's own test suite uses (e.g.
    `coordinator/bin/tests/test_percolate_identity_check_gate.py`), so this
    harness's import never collides with, or is confused for, a `pytest`
    collection of the real module."""
    spec = importlib.util.spec_from_file_location(
        "publish_full_payload_proof", _BIN_DIR / "publish.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rewrite_rows_dest_root(rows: List[str], scratch_dest_root: Path) -> List[str]:
    """Rewrite every resolved row's `dest` field (index 3) from its real,
    machine-local-resolved destination root to `scratch_dest_root`,
    preserving `dest_subdir` and every other field untouched.

    The real dest root is derived from the resolved rows THEMSELVES, not a
    second machine-local call: `claude-klabauter-publish-repo-toplevel`'s
    own row has an empty `dest_subdir`, so its resolved `dest` field IS the
    real dest root exactly (§ this repo's own `setup/publish-targets.
    portable` header comment on field shapes). Every other row's `dest` is
    then rewritten by computing its path relative to that real root and
    re-anchoring under `scratch_dest_root` -- so `sample-row`'s
    `<real_root>/coordinator_core` becomes `<scratch_root>/coordinator_core`
    and the toplevel row's `<real_root>` becomes `<scratch_root>` itself.

    Considered and rejected: a machine-local registry env-var override
    (`MACHINE_LOCAL_REGISTRY_DIR` or a per-key override). Probed live: the
    REAL installed `machine-local` reader (not this repo's forwarder;
    `${COORDINATOR_SETTINGS_HOME}/bin/machine-local`) honors
    `MACHINE_LOCAL_REGISTRY_DIR` (confirmed: pointing it at an empty
    scratch dir made `publish.mirrors.claude_klabauter.path` resolve
    "not found" instead of the real path) but does NOT honor a per-key
    `MACHINE_LOCAL_<KEY>` override (confirmed: still returned the real
    path with one set) -- so a whole-registry-dir override would also have
    to re-supply every OTHER key the rest of the publish pipeline resolves
    (e.g. whatever `repos.*` key backs the engine root's resolution), which is
    a second, parallel, drift-prone registry-authoring surface this
    function's simpler row-rewrite avoids entirely.

    Raises `RuntimeError` if no row named `claude-klabauter-publish-repo-
    toplevel` is present in `rows` -- the real-dest-root derivation has no
    fallback; this is a loud abort, not a guess.
    """
    toplevel_row = next(
        (r for r in rows if r.split("|", 1)[0] == _TOPLEVEL_ROW_NAME), None
    )
    if toplevel_row is None:
        raise RuntimeError(
            f"percolate-full-payload-proof: no row named {_TOPLEVEL_ROW_NAME!r} "
            f"in the resolved row set -- cannot derive the real destination "
            f"root to rewrite. Resolved names: "
            f"{sorted({r.split('|', 1)[0] for r in rows})}"
        )
    real_dest_root = Path(toplevel_row.split("|")[3])

    rewritten: List[str] = []
    for row in rows:
        fields = row.split("|")
        real_dest = Path(fields[3])
        rel = real_dest.relative_to(real_dest_root)
        fields[3] = str(scratch_dest_root / rel) if str(rel) != "." else str(scratch_dest_root)
        rewritten.append("|".join(fields))
    return rewritten


def _declared_row_names(rows: List[str]) -> List[str]:
    """Every `claude-klabauter*` row name `load_targets()` actually declared
    for this run -- derived from the resolved rows themselves (never a
    constant this script maintains separately), so a row added to or
    removed from `setup/publish-targets.portable` changes what this harness
    expects to see processed without anyone having to remember to update a
    second list here."""
    return sorted(
        {r.split("|", 1)[0] for r in rows if r.split("|", 1)[0].startswith(_ROW_NAME_PREFIX)}
    )


def _parse_skipped_row_names(stdout_text: str) -> List[str]:
    """Every row name `publish.py` printed a "Skipping {name}[.( ]" line for
    in this pass's captured stdout -- the same signal this harness's own
    end-of-run-leg parsing already trusts over a bare exit code (§ module
    docstring's `_parse_end_of_run_leg_status`): a row silently absent from
    the processed set is exactly the "skipped gate reads as clean" failure
    class this workstream exists to close, just one level up, at the ROW
    rather than the leg."""
    return sorted(
        {name for name in _SKIPPING_LINE_RE.findall(stdout_text) if name.startswith(_ROW_NAME_PREFIX)}
    )


def _git_init_scratch_dest(scratch_dest_root: Path) -> None:
    """`git init` the scratch destination -- a plain `tempfile.mkdtemp()`
    directory has no `.git` marker at all, which is NOT the shape a real
    destination clone has (the real klabauter clone is a git checkout with
    an unborn HEAD and zero commits, per `state/audits/2026-08-05-klabauter
    -scrub-and-gate-both-silent.md` § Q1's live reproduction). Without this,
    `_ensure_dest_ready`'s (coordinator/bin/publish.py) git-ancestor
    bootstrap check refuses every row whose `dest_subdir` names a directory
    that does not already exist under the scratch root -- a false failure
    of the SCRATCH FIXTURE, not of the pipeline under test. `git init`
    alone (no commit, no remote) reproduces the real clone's actual git
    shape without ever touching a remote or creating history the
    convergence proof does not need.

    Purely local and disposable -- never a remote, never
    `$HOME/X/claude-klabauter` (see module docstring)."""
    import subprocess

    from coordinator_core.win_portability import no_console_creationflags

    subprocess.run(
        ["git", "init", "-q", str(scratch_dest_root)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **no_console_creationflags(),
    )


def _hash_tree(root: Path) -> Dict[str, str]:
    """sha256 every PUBLISHED file under `root`, keyed by POSIX-normalized
    path relative to `root` -- the byte-level convergence oracle. Skips the
    `.git/` directory this harness itself creates (§ `_git_init_scratch_dest`)
    -- git's own internal bookkeeping is not part of the publish payload, and
    is not required to be byte-identical between two runs for the payload
    itself to have converged. Directory structure is otherwise implied by
    the key set (an empty directory that appears only in one pass is
    invisible to a pure file hash, which is correct here: an inject/sync
    pass leaving a stray empty directory behind is not the "raw source left
    behind" failure class this proof targets)."""
    result: Dict[str, str] = {}
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.relative_to(root).parts:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result[path.relative_to(root).as_posix()] = digest
    return result


def _diff_trees(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    """Human-readable diff lines between two `_hash_tree` results -- added,
    removed, and changed paths. Empty list means byte-identical trees."""
    lines: List[str] = []
    before_keys, after_keys = set(before), set(after)
    for path in sorted(after_keys - before_keys):
        lines.append(f"  + {path} (new in pass 2)")
    for path in sorted(before_keys - after_keys):
        lines.append(f"  - {path} (present after pass 1, gone after pass 2)")
    for path in sorted(before_keys & after_keys):
        if before[path] != after[path]:
            lines.append(f"  ~ {path} (content differs between pass 1 and pass 2)")
    return lines


class PinNotHonoredError(RuntimeError):
    """Raised whenever this harness cannot make both passes publish from the
    same resolved commit sha(s) (§ module docstring 'SOURCE PIN') -- either
    up front, before either pass runs (`_resolve_pinned_commit_shas` cannot
    resolve some contributing root's toplevel or HEAD), or mid-run (a pass's
    own `_git_rev_parse` wrapper, `_make_pinned_rev_parse`, is asked to
    resolve HEAD for a toplevel the pre-run pin walk never covered). Always
    a loud, unhandled-by-default abort -- a convergence verdict measured
    against a source pin that quietly failed to hold is worse than no
    verdict at all, exactly the failure class this whole mechanism exists to
    close."""


_PROVENANCE_LINE_RE = re.compile(
    r"^\s*Provenance: (\S+) shipped from (\S+)", re.MULTILINE
)


def _parse_provenance_lines(stdout_text: str) -> Dict[str, str]:
    """Every `Provenance: <root> shipped from <sha>` line `publish.py`'s
    `run_pre_sync_gates` already prints per contributing root, per pass --
    the cheapest independent verification hook for the source pin this
    harness applies (§ module docstring 'SOURCE PIN'). Compared pass 1
    against pass 2 in the verdict, in addition to and independent of the
    byte-level `_hash_tree` comparison: if the two maps are not identical,
    the pin did not hold even though this harness intended it to."""
    return dict(_PROVENANCE_LINE_RE.findall(stdout_text))


def _resolve_pinned_commit_shas(publish_module, real_rows: List[str]) -> Dict[str, str]:
    """Resolve, ONCE before either pass runs, the exact commit sha every
    contributing root of every declared row is at RIGHT NOW -- keyed by that
    root's git toplevel (§ module docstring 'SOURCE PIN' for why toplevel,
    not root, is the key). `real_rows` must be the UNREWRITTEN rows
    `percolate.targets.load_targets` itself resolved (never the
    scratch-dest-rewritten rows `_rewrite_rows_dest_root` produces) --
    `dest` is irrelevant here, only `source_dir`/`source_map` (read via
    `publish_module.parse_target_row` / `publish_module._contributing_roots`,
    the exact same resolution `run_pre_sync_gates` performs) matter.

    Raises `PinNotHonoredError` (never falls back to publishing that root
    unpinned) if any contributing root cannot be resolved to a git toplevel
    or a HEAD sha -- e.g. not inside a git work tree, an unborn HEAD, or
    `git` missing from `PATH`."""
    pins: Dict[str, str] = {}
    for row in real_rows:
        target = publish_module.parse_target_row(row)
        for root in publish_module._contributing_roots(target):
            toplevel = publish_module._git_rev_parse(root, "--show-toplevel")
            if toplevel is None:
                raise PinNotHonoredError(
                    f"percolate-full-payload-proof: cannot pin a commit sha for "
                    f"contributing root {root} ({target.name}) -- not inside a "
                    f"git work tree (or 'git' is not on PATH)."
                )
            if toplevel in pins:
                continue
            sha = publish_module._git_rev_parse(Path(toplevel), "HEAD")
            if sha is None:
                raise PinNotHonoredError(
                    f"percolate-full-payload-proof: cannot pin a commit sha for "
                    f"contributing root {root} ({target.name}) -- 'git -C "
                    f"{toplevel} rev-parse HEAD' failed (unborn HEAD, or 'git' "
                    f"is not on PATH)."
                )
            pins[toplevel] = sha
    return pins


def _make_pinned_rev_parse(real_rev_parse, pinned_shas: Dict[str, str], head_movement_notes: List[str], pass_number: int):
    """Build a `_git_rev_parse`-shaped wrapper (coordinator/bin/publish.py)
    that answers every `("HEAD",)` call for a pinned root's toplevel with
    the sha `_resolve_pinned_commit_shas` captured before either pass ran,
    instead of resolving live HEAD -- the mechanism that makes both passes
    publish from identical source bytes regardless of any commit a peer
    lands in between (§ module docstring 'SOURCE PIN').

    Every other call shape (`--show-toplevel`, `--show-prefix`, or a
    `("HEAD",)` call whose toplevel is not in `pinned_shas`... which raises,
    see below) passes straight through to `real_rev_parse` untouched -- this
    narrows to exactly the one call shape (`_git_materialize_ref`'s and
    `run_pre_sync_gates`'s Provenance-line HEAD resolution) that decides
    what gets published. Never intercepts a DESTINATION-side HEAD read --
    `write_lastsync_marker` reads the destination's HEAD through the
    unrelated `_git_head` helper, never through `_git_rev_parse`, so no
    destination-side call is ever routed through this wrapper at all.

    Appends a human-readable note to `head_movement_notes` (informational,
    never a failure -- see module docstring) whenever the LIVE HEAD at call
    time has moved past the pin, so a peer's concurrent commit landing
    mid-run is visible in the verdict rather than silently invisible now
    that pinning has already neutralized its effect on the published bytes.

    Raises `PinNotHonoredError` if a `("HEAD",)` call's resolved toplevel has
    no entry in `pinned_shas` -- `_resolve_pinned_commit_shas` is supposed to
    have pinned every contributing root either pass could ever touch before
    either pass starts; a miss here means that precondition broke, and this
    harness fails loud rather than silently resolving an unpinned live HEAD
    for just that one call."""

    def _pinned_rev_parse(path, *args):
        if args != ("HEAD",):
            return real_rev_parse(path, *args)
        toplevel = real_rev_parse(path, "--show-toplevel")
        if toplevel is None or toplevel not in pinned_shas:
            raise PinNotHonoredError(
                f"percolate-full-payload-proof: pass {pass_number} tried to "
                f"resolve HEAD for {path} (toplevel {toplevel!r}), which was "
                f"never pinned by _resolve_pinned_commit_shas before either "
                f"pass started -- refusing to silently measure convergence "
                f"against a moving, unpinned HEAD."
            )
        pinned = pinned_shas[toplevel]
        live = real_rev_parse(path, "HEAD")
        if live is not None and live != pinned:
            head_movement_notes.append(
                f"pass {pass_number}: {toplevel} moved to {live} mid-run "
                f"(pinned to {pinned} -- publish still used the pin, not the "
                f"live HEAD)"
            )
        return pinned

    return _pinned_rev_parse


def _parse_end_of_run_leg_status(stderr_text: str) -> Dict[str, str]:
    """Classify each end-of-run leg's outcome for one pass as one of
    'ran-clean', 'ran-failed', 'skipped-advisory', or 'unknown' (never
    silently absorbed into a bare pass/fail) by matching the EXACT marker
    strings `dispatch_end_of_run_identity_check` /
    `dispatch_end_of_run_install_doc_payload_check` (coordinator/bin/
    publish.py) print -- not by inferring behavior from the process exit
    code alone, which is exactly how a skipped gate read as clean in the
    original defect this whole workstream is closing."""
    status = {
        "identity_check": "unknown",
        "install_doc_payload_check": "unknown",
        "unscanned_published_check": "unknown",
    }

    if _IDENTITY_FAIL_MARKER in stderr_text:
        status["identity_check"] = "ran-failed"
    elif _IDENTITY_SKIP_MARKER in stderr_text:
        status["identity_check"] = "skipped-advisory"
    elif _IDENTITY_RAN_CLEAN_MARKER not in stderr_text:
        # Neither a failure line nor a skip line printed at all -- absence
        # of stderr chatter for a leg that ran clean is the EXPECTED shape
        # (dispatch_end_of_run_identity_check only prints on skip or
        # nonzero exit), so this is the "ran and found nothing to say"
        # case, not evidence it never ran.
        status["identity_check"] = "ran-clean-silent"

    if _INSTALL_DOC_FAIL_MARKER in stderr_text:
        status["install_doc_payload_check"] = "ran-failed"
    elif _INSTALL_DOC_ADVISORY_MARKER in stderr_text:
        status["install_doc_payload_check"] = "skipped-advisory"
    else:
        status["install_doc_payload_check"] = "ran-clean-silent"

    if _UNSCANNED_FAIL_MARKER in stderr_text:
        status["unscanned_published_check"] = "ran-failed"
    elif _UNSCANNED_NOTE_MARKER in stderr_text:
        status["unscanned_published_check"] = "ran-clean-with-ratified-exceptions"
    else:
        status["unscanned_published_check"] = "ran-clean-silent"

    return status


def _run_one_pass(
    scratch_dest_root: Path,
    pass_number: int,
    pinned_shas: Dict[str, str],
    head_movement_notes: List[str],
) -> "PassResult":
    """Run one `publish.main([])` invocation with `load_targets` rewired to
    the REAL resolved rows, dest-root-rewritten onto `scratch_dest_root`
    (§ `_rewrite_rows_dest_root`). Captures stdout/stderr via monkeypatched
    `sys.stdout`/`sys.stderr` around the call.

    `publish._git_rev_parse` is ALSO rewired here, per pass, to
    `_make_pinned_rev_parse(..., pinned_shas, ...)` (§ module docstring
    'SOURCE PIN') -- both passes publish from the SAME pre-resolved commit
    sha(s), never a freshly re-resolved live HEAD, so a peer's concurrent
    commit landing between pass 1 and pass 2 cannot manufacture a false
    convergence failure.

    `publish.py`'s own row-level prints (`=== name (mode) ===` headers,
    "Skipping", "Synced:", "Provenance:") go through functions declared as
    `def foo(..., out: IO[str] = sys.stdout)` -- a REGULAR Python default
    parameter, bound ONCE at function-definition time (i.e. at module
    import), not re-resolved per call. `main()` never passes `out=`
    explicitly at these call sites (verified: `process_target(...)` at its
    one call site in `main()` carries no `out=` kwarg), so if the module
    were imported once and reused across both passes (as an earlier version
    of this harness did), every one of those prints would be bound to
    whatever `sys.stdout` object existed at THAT single import moment --
    forever after, regardless of any later `sys.stdout = captured_out`
    reassignment here. That is not a hypothetical: verified live by adding
    row-completeness parsing (§ `_processed_rows`/`_parse_skipped_row_names`)
    and finding it saw zero rows despite `Synced:` lines being visibly
    present in the real terminal output -- the captured text was missing
    every row-level print, silently, while OTHER prints (bare `print(...)`
    calls with no `file=` argument, which DO look up `sys.stdout`
    dynamically per call, e.g. the per-file NEW/UPDATE diff lines) came
    through fine. Same escape path exists for `err: IO[str] = sys.stderr`,
    which the end-of-run leg markers this harness's own `_parse_end_of_run_
    leg_status` depends on are printed through.

    Fixed at the root, without editing `publish.py`: `_load_publish_module()`
    is called HERE, fresh, per pass, AFTER the stream swap below -- so every
    `out=sys.stdout`/`err=sys.stderr` default binds to `captured_out`/
    `captured_err` at THIS import, not to the process's real streams. A
    second import per pass is by construction the only way to make a
    stale-default-bound print in an unmodified sibling module observe a
    stream swap performed by its caller."""
    from percolate.targets import load_targets as _real_load_targets  # noqa: E402

    captured_out, captured_err = io.StringIO(), io.StringIO()
    real_stdout, real_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = captured_out, captured_err
    try:
        publish = _load_publish_module()

        # § module docstring 'SOURCE PIN' -- rewire THIS pass's freshly
        # -imported `_git_rev_parse` so every HEAD resolution answers from
        # `pinned_shas` (captured once, before either pass ran) instead of
        # re-invoking live `git rev-parse HEAD`. No try/finally restore here
        # by design, not oversight: `publish` is guaranteed fresh-per-call
        # (`_load_publish_module()` above does a private-name `importlib`
        # load, never a cached/memoized import), so this mutated attribute
        # dies with the module object at the end of THIS pass. If
        # `_load_publish_module()` is ever changed to cache or memoize its
        # result, this line becomes a cross-pass leak -- restore
        # `publish._git_rev_parse` to its pre-mutation value in a `finally`
        # at that point.
        publish._git_rev_parse = _make_pinned_rev_parse(
            publish._git_rev_parse, pinned_shas, head_movement_notes, pass_number
        )

        declared_rows: List[str] = []

        def _rewritten_load_targets(setup_dir, *, target_filter="", **kwargs):
            real_rows = _real_load_targets(setup_dir, target_filter=target_filter, **kwargs)
            declared_rows[:] = _declared_row_names(real_rows)
            return _rewrite_rows_dest_root(real_rows, scratch_dest_root)

        publish.load_targets = _rewritten_load_targets

        exit_code = publish.main([])
    finally:
        sys.stdout, sys.stderr = real_stdout, real_stderr

    stdout_text, stderr_text = captured_out.getvalue(), captured_err.getvalue()
    skipped_rows = _parse_skipped_row_names(stdout_text)
    return PassResult(
        pass_number=pass_number,
        exit_code=exit_code,
        stdout=stdout_text,
        stderr=stderr_text,
        leg_status=_parse_end_of_run_leg_status(stderr_text),
        tree_hash=_hash_tree(scratch_dest_root),
        declared_rows=declared_rows,
        skipped_rows=skipped_rows,
        missing_rows=sorted(set(declared_rows) - set(skipped_rows) - _processed_rows(stdout_text)),
        provenance=_parse_provenance_lines(stdout_text),
    )


def _processed_rows(stdout_text: str) -> set:
    """Row names whose block actually ran a sync (printed a `Synced:` line
    or a `Provenance:` line under their own `=== name (mode) ===` header) --
    used only to catch a row that vanished from the output WITHOUT ever
    printing a "Skipping" line at all (a silent drop, distinct from an
    explicit skip), so `missing_rows` never depends on `_ROW_NAME_PREFIX`
    rows being well-behaved about naming their own skip."""
    processed = set()
    current = None
    for line in stdout_text.splitlines():
        header = re.match(r"=== (\S+) \(", line)
        if header:
            current = header.group(1)
            continue
        if current and current.startswith(_ROW_NAME_PREFIX) and (
            line.strip().startswith("Synced:") or line.strip().startswith("Provenance:")
        ):
            processed.add(current)
    return processed


class PassResult:
    def __init__(
        self, *, pass_number, exit_code, stdout, stderr, leg_status, tree_hash,
        declared_rows, skipped_rows, missing_rows, provenance,
    ):
        self.pass_number = pass_number
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.leg_status = leg_status
        self.tree_hash = tree_hash
        self.declared_rows = declared_rows
        self.skipped_rows = skipped_rows
        self.missing_rows = missing_rows
        self.provenance = provenance


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Publish the full klabauter payload twice into a wiped scratch "
            "destination via the real publish.py CLI path, and prove the "
            "second run converges byte-identically with the first."
        ),
    )
    p.add_argument(
        "--keep-scratch",
        action="store_true",
        help="Do not delete the scratch destination on exit (default: removed).",
    )
    p.add_argument(
        "--allow-dirty-tree-override",
        action="store_true",
        help="Retired no-op: a dirty tree never gated this run.",
    )
    p.add_argument(
        "--i-understand-the-risk",
        action="store_true",
        help="Retired no-op, accepted for compatibility.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_engine_on_path

    # The engine root must be on sys.path before `_git_init_scratch_dest`'s
    # coordinator_core import runs: this file is also published into the
    # claude-klabauter mirror, where coordinator_core is NOT pip-installed and
    # the interpreter's sys.path[0] is this bin/ directory, not the checkout
    # root. Same bootstrap as coordinator/bin/coordinator-lesson-add (9b979ee5f).
    require_engine_on_path(__file__)

    args = build_arg_parser().parse_args(argv)

    pin_module = _load_publish_module()  # preflight: fail fast on an import error before touching disk

    # § module docstring 'SOURCE PIN' -- resolve the commit sha every
    # contributing root is at RIGHT NOW, ONCE, before either pass runs, so
    # both passes publish from the exact same source bytes regardless of any
    # commit a peer lands on this shared branch in between. Deliberately
    # done here (before the scratch destination even exists) rather than
    # lazily inside pass 1 -- the pin is a precondition of both passes, not
    # a side effect of running the first one.
    from percolate.targets import load_targets as _real_load_targets_for_pin

    percolate_root, _percolate_root_rung = pin_module._resolve_percolate_root_and_rung()
    setup_dir_for_pin = percolate_root / "setup"
    try:
        real_rows_for_pin = _real_load_targets_for_pin(setup_dir_for_pin)
        pinned_shas = _resolve_pinned_commit_shas(pin_module, real_rows_for_pin)
    except (pin_module.TargetsError, PinNotHonoredError) as exc:
        print(
            f"percolate-full-payload-proof: FAILED to establish the commit-sha "
            f"source pin before running either pass -- {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        "percolate-full-payload-proof: pinned commit sha(s) for this run -- "
        "both passes publish from these, regardless of any commit landed "
        "after this point:"
    )
    for toplevel, sha in sorted(pinned_shas.items()):
        print(f"  {toplevel} @ {sha}")

    head_movement_notes: List[str] = []

    scratch_dest_root = Path(tempfile.mkdtemp(prefix="klabauter-full-payload-proof-"))
    print(f"percolate-full-payload-proof: scratch destination: {scratch_dest_root}")
    _git_init_scratch_dest(scratch_dest_root)

    try:
        try:
            pass1 = _run_one_pass(scratch_dest_root, 1, pinned_shas, head_movement_notes)
            pass2 = _run_one_pass(scratch_dest_root, 2, pinned_shas, head_movement_notes)
        except PinNotHonoredError as exc:
            print(
                f"\npercolate-full-payload-proof: FAILED -- the commit-sha source "
                f"pin could not be honoured mid-run -- {exc}",
                file=sys.stderr,
            )
            return 1

        diff = _diff_trees(pass1.tree_hash, pass2.tree_hash)
        converged = not diff

        all_rows_processed = (
            not pass1.skipped_rows and not pass1.missing_rows
            and not pass2.skipped_rows and not pass2.missing_rows
        )

        provenance_pinned = pass1.provenance == pass2.provenance

        overall_ok = (
            pass1.exit_code == 0
            and pass2.exit_code == 0
            and converged
            and all_rows_processed
            and provenance_pinned
        )

        print("\n=============== VERDICT ===============")
        print("PASS" if overall_ok else "FAIL")
        print(f"  pass 1 exit code: {pass1.exit_code}")
        print(f"  pass 2 exit code: {pass2.exit_code}")
        print(f"  pass 1 files published: {len(pass1.tree_hash)}")
        print(f"  pass 2 files published: {len(pass2.tree_hash)}")
        print(f"  converged (byte-identical pass1 vs pass2): {converged}")
        if diff:
            print("  divergence:")
            for line in diff:
                print(line)
        print("  pinned commit sha(s) this run published from (§ 'SOURCE PIN'):")
        for toplevel, sha in sorted(pinned_shas.items()):
            print(f"    {toplevel} @ {sha}")
        print(f"  source pin honoured (pass1 vs pass2 Provenance lines identical): {provenance_pinned}")
        if not provenance_pinned:
            print("    pass 1 provenance:")
            for root, sha in sorted(pass1.provenance.items()):
                print(f"      {root} @ {sha}")
            print("    pass 2 provenance:")
            for root, sha in sorted(pass2.provenance.items()):
                print(f"      {root} @ {sha}")
        if head_movement_notes:
            print(
                "  NOTE: HEAD moved on a pinned root mid-run (pin honoured -- "
                "published bytes unaffected):"
            )
            for note in head_movement_notes:
                print(f"    {note}")
        for pass_result in (pass1, pass2):
            declared_n = len(pass_result.declared_rows)
            not_processed = sorted(set(pass_result.skipped_rows) | set(pass_result.missing_rows))
            processed_n = declared_n - len(not_processed)
            print(
                f"  pass {pass_result.pass_number} rows: {processed_n} of {declared_n} "
                f"declared claude-klabauter* rows processed"
            )
            if not_processed:
                print(f"    NOT PROCESSED: {', '.join(not_processed)}")
                print(
                    "    see this pass's stdout/stderr below for the skip reason"
                )
        print("  end-of-run leg status, pass 1:")
        for leg, status in pass1.leg_status.items():
            print(f"    {leg}: {status}")
        print("  end-of-run leg status, pass 2:")
        for leg, status in pass2.leg_status.items():
            print(f"    {leg}: {status}")
        print("=========================================")

        print("\n--- pass 1 stdout (tail) ---")
        print("\n".join(pass1.stdout.splitlines()[-40:]))
        print("--- pass 1 stderr ---")
        print(pass1.stderr)
        print("--- pass 2 stdout (tail) ---")
        print("\n".join(pass2.stdout.splitlines()[-40:]))
        print("--- pass 2 stderr ---")
        print(pass2.stderr)

        return 0 if overall_ok else 1
    finally:
        if args.keep_scratch:
            print(f"percolate-full-payload-proof: --keep-scratch set; leaving {scratch_dest_root} in place.")
        else:
            shutil.rmtree(scratch_dest_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
