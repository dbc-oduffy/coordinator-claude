"""percolate-mirror.py — publish EVERY registered row of ONE mirror in a
single round, so a caller names a mirror and nothing else.

Why this exists (PM ruling 2026-08-18, in session): publishing to a registered
mirror should not require a caller to assemble an invocation. `percolate-round`
is single-target by contract, so a mirror carrying N rows needed N rounds — and
because `--delta` skips a row's WORK but never its VERIFICATION, every one of
those rounds re-scanned the full destination tree. Measured against
`claude-klabauter` (9 rows, 3,949 tracked files) the end-of-run legs alone were
identity 29.7s + unscanned-published 5.2s + function gate 11.4s + argv-parity
5.2s, paid nine times.

`publish.py` already amortises exactly that: ONE invocation loads the 4-tier
target set and the percolate store once and reuses them across every matching
row (§ its own `target` help text). Measured the same day: 8 rows, 8/8, 450s
total. This entry point owns that single invocation plus the lock, the
crash-recovery pre-flight, the commit and the push.

Negative-spec — this module SEQUENCES, it does not reimplement. Every leg
delegates to `percolate-round.py`'s own helpers (imported by file path, since a
dashed filename is not importable as a module name): `_resolve_dest`,
`_resolve_repo_root`, `_round_held_lock`, `_rows_scan_lists`,
`_extract_change_lines`, `_read_fresh_round_manifest`, `_pathspec_from_manifest`,
`_push_dest`. It does NOT own gate policy, does NOT widen any allowlist, and
does NOT decide a seed amendment — those stay where they are.

The commit pathspec keeps `percolate-round`'s AC7 provenance invariant: it is
derived from `publish.py`'s own reported change lines, never from a survey of
the destination tree.

Spec backlink: state/sizings/2026-08-18-one-entry-point-owns-the-mirror-publish.yaml
"""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

_BIN_DIR = Path(__file__).resolve().parent
_LIB_DIR = _BIN_DIR.parent / "lib"


def _load_round_module():
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    spec = importlib.util.spec_from_file_location(
        "percolate_round", _BIN_DIR / "percolate-round.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def __getattr__(name: str):
    if name in ("_round",):
        _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _require_percolate_engine(root: str) -> None:
    """Fail loud when `root` is an engine tree with no percolate package.

    The resolvable-but-wrong case the locator rung order above makes unlikely
    and this makes impossible to mistake: a published engine mirror carries
    `coordinator_core` but NOT `coordinator_core/percolate` (percolate is
    source-only), so a bootstrap that lands on one imports cleanly and then
    dies several frames later on `from percolate.targets import ...`, naming a
    module rather than the root. Checked against the FILESYSTEM, not an import
    attempt: by this point `coordinator_core` is already bound and an
    ImportError here would be indistinguishable from a genuine packaging
    fault."""
    if (Path(root) / "coordinator_core" / "percolate").is_dir():
        return
    raise RuntimeError(
        f"percolate-mirror: resolved engine root '{root}' has no "
        "coordinator_core/percolate — that is a PUBLISHED ENGINE MIRROR, not "
        "the source checkout percolate publishes from. Run this from the "
        "engine SOURCE checkout, or set COORDINATOR_ENGINE_SOURCE_ROOT to it."
    )


def _bootstrap_engine() -> None:
    """Resolve the engine root and bind the `_round` module global. Called
    once, first thing in `main()` (or lazily via `__getattr__` above, for a
    caller that reaches for `_round` before `main()` runs).

    The engine root is put on `sys.path` EXPLICITLY here, not inherited from
    `_load_round_module()` below. That call does happen to leave the engine
    reachable — `percolate-round.py` inserts `coordinator/lib` at its own import
    time — but depending on it made this file's bootstrap an undeclared
    side effect of a sibling's import order: reorder or slim that sibling and
    this import dies with `ModuleNotFoundError: coordinator_core` on the
    published mirror, with nothing here naming the dependency. Declaring it is
    the same seam ~175 other CLIs under this directory already use.

    LOCATOR AXIS, NOT DISPATCH — and that is the whole point of this function.
    DR-326 splits the two questions: `COORDINATOR_ENGINE_ROOT` answers "which
    engine executes" (dispatch, the published mirror on a conformant box) and
    `COORDINATOR_ENGINE_SOURCE_ROOT` answers "where is the source checkout"
    (locator). A PUBLISH TOOL IS ON THE LOCATOR AXIS BY CONSTRUCTION: percolate
    is authored in the source checkout and publishes FROM it INTO the mirror, so
    the engine it must import is the one it is about to publish, never the one
    it is about to overwrite. Binding it to the dispatch root made the mirror
    its own prerequisite — on a box whose dispatch root is the published mirror
    (every cloud container: `COORDINATOR_ENGINE_ROOT=/root/klabauter`), the
    mirror carries no `coordinator_core/percolate` package at all, so the only
    tool that can refresh the mirror could not run, and the staler the mirror
    got the more certainly it could not be updated. `require_colocated_engine_
    on_path` is the existing locator-axis seam with the right rung order:
    self-location FIRST (this file's own checkout, which is by definition the
    source tree a percolation publishes from), registry ladder second, and an
    ambient `COORDINATOR_ENGINE_ROOT` never consulted while self-location hits.
    `percolate-round.py`, whose helpers this file drives, already binds on that
    same axis (see its `_resolve_central_state` note) — this stops the two
    contradicting each other.

    MUST run before `_load_round_module()` executes below: `percolate-round.py`
    binds `coordinator_core` at ITS OWN module level off a bare self-location
    `sys.path` insert — once that exec_module() call runs, whatever root it
    happened to bind wins, and no later `sys.path` insert here can rebind an
    already-imported package.
    NOTE `_BIN_DIR / "lib"`, not `_LIB_DIR` — this file's `_LIB_DIR` is
    `coordinator/lib` (the percolate helpers), while `cc_invoke` lives in
    `coordinator/bin/lib`. They are different directories.
    """
    if all(n in globals() for n in ("_round",)):
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import _front_insert_on_path, require_colocated_engine_on_path

    # rung 2 falls through to `_resolve_claude_klabauter_root()`, the DISPATCH ladder,
    # prints ("set COORDINATOR_ENGINE_SOURCE_ROOT") true rather than advice
    source_override = (os.environ.get("COORDINATOR_ENGINE_SOURCE_ROOT") or "").strip()
    if source_override and os.path.isdir(source_override):
        root = _front_insert_on_path(source_override)
    else:
        root = require_colocated_engine_on_path(__file__)
    # LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
    import coordinator_core  # noqa: F401

    _require_percolate_engine(root)

    _round_ = _load_round_module()
    _round_._bootstrap_engine()

    for _name, _value in (
        ("_round", _round_),
    ):
        globals().setdefault(_name, _value)


def _mirror_groups(percolate_root: str) -> Optional[Dict[str, List[str]]]:
    """Registered target names grouped by the git WORKTREE ROOT their dest
    resolves into, in `publish-targets.portable` order.

    `load_targets` returns RESOLVED rows — field 2 is the absolute source dir
    and field 3 the absolute dest — so the portable file's `publish-mirror:*`
    sigil is already gone by the time it gets here and cannot be the key.
    Worktree root is the better key anyway: it is what "one mirror" actually
    means. Rows landing in sibling subdirectories of a single mirror
    (`<mirror>`, `<mirror>/bin`, `<mirror>/coordinator/lib`) resolve to the
    same root and so group together, which is exactly the set one publish
    invocation and one lock must cover."""
    _bootstrap_engine()
    from percolate.targets import TargetsError, load_targets  # noqa: E402

    setup_dir = Path(percolate_root) / "setup"
    try:
        rows = load_targets(setup_dir, target_filter=None)
    except TargetsError as exc:
        print(exc.message, file=sys.stderr)
        return None

    groups: Dict[str, List[str]] = {}
    for row in rows:
        fields = row.split("|")
        if len(fields) < 4:
            continue
        root = _round._resolve_repo_root(fields[3])
        if root is None:
            continue
        groups.setdefault(root, []).append(fields[0])
    return groups


def _row_paths(percolate_root: str) -> Dict[str, tuple]:
    from percolate.targets import TargetsError, load_targets  # noqa: E402

    try:
        rows = load_targets(Path(percolate_root) / "setup", target_filter=None)
    except TargetsError:
        return {}

    paths: Dict[str, tuple] = {}
    for row in rows:
        fields = row.split("|")
        if len(fields) >= 4:
            paths[fields[0]] = (fields[2], fields[3])
    return paths


def _select_mirror(selector: str, groups: Dict[str, List[str]]) -> Optional[str]:
    if selector in groups:
        return selector

    normalized = selector.replace("-", "_").lower()
    matches = [
        root
        for root in groups
        if Path(root).name.replace("-", "_").lower() == normalized
    ]
    if len(matches) == 1:
        return matches[0]

    owning = [root for root, targets in groups.items() if selector in targets]
    if len(owning) == 1:
        return owning[0]

    ambiguous = sorted(set(matches + owning))
    if len(ambiguous) > 1:
        print(
            f"percolate-mirror: '{selector}' is ambiguous across {ambiguous}; "
            "name the mirror worktree root exactly.",
            file=sys.stderr,
        )
    return None


def _run_gate_legs(
    repo_root: str,
    manifest_added: List[str],
    targets: List[str],
    percolate_root: str,
    tmp: Path,
) -> Optional[int]:
    _bootstrap_engine()
    identity_file = Path(percolate_root) / "setup" / ".percolate-identity"
    peer_repos_file = _round._resolve_central_state()
    medium_total = 0
    crlf_dismissed = 0
    unreliable_anchor: List[tuple] = []
    real_drift: List[tuple] = []

    row_paths = _row_paths(percolate_root)
    for target in targets:
        # Branch 0 is a per-target FIRST-RUN SETUP check (it fails
        # MISSING_IGNORE on a row with no `.percolate-ignore` of its own).
        paths = row_paths.get(target)
        if paths is None:
            print(
                f"percolate-mirror: '{target}' is not in the resolved targets "
                "table; cannot run its gate legs.",
                file=sys.stderr,
            )
            return _round._EXIT_FAIL
    row_dests = {target: row_paths[target][1] for target in targets}
    try:
        scan_lists = _round._rows_scan_lists(repo_root, manifest_added, row_dests)
    except ValueError as exc:
        _round._print_step_failure("scan-file-list build", [], str(exc))
        return _round._EXIT_FAIL

    for target in targets:
        source_dir, dest = row_paths[target]
        scan_file_list = scan_lists[target]
        if not scan_file_list:
            continue

        scan_files_path = tmp / f"scan-files-{target}.txt"
        scan_files_path.write_text(
            "\n".join(scan_file_list) + ("\n" if scan_file_list else ""),
            encoding="utf-8", newline="\n",
        )

        scan_cmd = [
            sys.executable,
            str(_round._PERCOLATE_GATE),
            "scan-secrets",
            "--files",
            str(scan_files_path),
            "--identity-file",
            str(identity_file),
            "--target",
            target,
            "--percolate-root",
            percolate_root,
        ]
        if peer_repos_file is not None:
            scan_cmd += ["--peer-repos-file", str(peer_repos_file)]
        scan = _round._run(scan_cmd, timeout=_round._ROUND_SCAN_LEG_TIMEOUT_SECS)
        print(scan.stdout)
        if scan.returncode == 2:
            print(
                f"percolate-mirror: HIGH-tier content leak detected on '{target}' "
                "— refusing to commit/push (already synced to dest; revert with "
                "`git -C <dest> reset --hard && git clean -fd`).",
                file=sys.stderr,
            )
            return _round._EXIT_FAIL
        if scan.returncode != 0:
            _round._print_step_failure("Step 2 (scan-secrets)", scan_cmd, scan.stderr)
            return _round._EXIT_FAIL
        medium_total += _round._count_medium_hits(scan.stdout)

        drift_cmd = [
            sys.executable,
            str(_round._PERCOLATE_GATE),
            "inverse-drift",
            target,
            "--percolate-root",
            percolate_root,
            "--dest",
            dest,
            "--files",
            str(scan_files_path),
            "--source-dir",
            source_dir,
            "--json",
        ]
        drift = _round._run(drift_cmd, timeout=_round._ROUND_SCAN_LEG_TIMEOUT_SECS)
        if drift.returncode != 0:
            _round._print_step_failure("Step 2b (inverse-drift)", drift_cmd, drift.stderr)
            return _round._EXIT_FAIL
        try:
            verdict = json.loads(drift.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            _round._print_step_failure(
                "Step 2b (inverse-drift) — malformed verdict",
                drift_cmd,
                f"{type(exc).__name__}: {exc}",
            )
            return _round._EXIT_FAIL

        if not verdict["anchor_reliable"]:
            unreliable_anchor.append((target, verdict["anchor_mode"]))
        if verdict["real_drift"]:
            real_drift.append((target, verdict))
        crlf_dismissed += len(verdict["dismissed_crlf_only"])

    print(
        f"=== percolate-mirror — gate reads: {medium_total} MEDIUM leak hit(s), "
        f"{len(real_drift)} real-drift row(s), {crlf_dismissed} CRLF-only "
        f"dismissal(s) across {len(targets)} row(s) ==="
    )
    for target, mode in unreliable_anchor:
        print(
            f"  anchor unreliable on '{target}' ({mode}) — the drift window "
            "reaches back over already-published history, so its commit list "
            "is not a drift verdict. Re-percolate to refresh the anchor."
        )
    for target, verdict in real_drift:
        print(f"  REAL DRIFT on '{target}' ({verdict['commits']} commit(s)):")
        for line in verdict["commit_lines"][:10]:
            print(f"    {line}")
        print(
            "    -> authored directly in dest and about to be overwritten. "
            "Back-port to source FIRST, then re-run."
        )
    if real_drift:
        print(
            "percolate-mirror: refusing to commit over real inverse drift.",
            file=sys.stderr,
        )
        return _round._EXIT_FAIL
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="percolate-mirror",
        description=(
            "Publish every registered row of ONE mirror in a single round: one "
            "publish.py invocation for all rows, under one dest lock, then commit "
            "and push."
        ),
    )
    parser.add_argument(
        "mirror",
        help=(
            "Mirror worktree root (the path at machine-local key "
            "`publish.mirrors.<key>.path` -- NOT `repos.claude_klabauter`, "
            "which names this box's DEPLOYED ENGINE clone and is refused as a "
            "publish dest), its bare name (claude-klabauter), or any registered "
            "target name landing in it."
        ),
    )
    parser.add_argument("--percolate-root", default=None)
    parser.add_argument(
        "--invocation-authorized",
        action="store_true",
        help=(
            "Skill/slash-command wrapper only: this invocation IS the confirm. "
            "Never set on a bare human CLI run or an unattended caller."
        ),
    )
    parser.add_argument("--yes", action="store_true")
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Stop before the push; print the state instead of pushing.",
    )
    parser.add_argument(
        "--no-delta",
        dest="delta",
        action="store_false",
        default=True,
        help=(
            "Force a full row re-derivation instead of skipping rows publish.py "
            "can prove unchanged. Verification is unconditional either way."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the resolved row set for the mirror and exit without publishing.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _bootstrap_engine()

    args = _build_parser().parse_args(argv)

    percolate_root = _round._resolve_percolate_root(args.percolate_root)
    if not percolate_root:
        print("percolate-mirror: could not resolve PERCOLATE_ROOT.", file=sys.stderr)
        return _round._EXIT_USAGE

    groups = _mirror_groups(str(percolate_root))
    if groups is None:
        print(
            "percolate-mirror: publish-target resolution failed (cause above).",
            file=sys.stderr,
        )
        return _round._EXIT_USAGE
    if not groups:
        print("percolate-mirror: no registered publish targets.", file=sys.stderr)
        return _round._EXIT_USAGE

    mirror_root = _select_mirror(args.mirror, groups)
    if mirror_root is None:
        print(
            f"percolate-mirror: no mirror matches '{args.mirror}'. Known: "
            f"{sorted(groups)}",
            file=sys.stderr,
        )
        return _round._EXIT_USAGE

    targets = groups[mirror_root]
    print(f"=== percolate-mirror {mirror_root} — {len(targets)} row(s) ===")
    for name in targets:
        print(f"  {name}")

    if args.list:
        return _round._EXIT_OK

    dest = _round._resolve_dest(targets[0], str(percolate_root))
    if dest is None:
        return _round._EXIT_USAGE
    repo_root = _round._resolve_repo_root(dest)
    if repo_root is None:
        print(
            f"percolate-mirror: could not resolve git worktree root for dest "
            f"'{dest}'.",
            file=sys.stderr,
        )
        return _round._EXIT_FAIL

    joined = ",".join(targets)

    try:
        with _round._round_held_lock(
            Path(repo_root),
            holder_label=f"percolate-mirror:{Path(mirror_root).name}",
            timeout=_round.publish_contention_wait_secs(),
        ):
            print(f"=== percolate-mirror {mirror_root} — publish ({len(targets)} rows, one invocation) ===")
            real_env = dict(os.environ)
            real_env[_round._INHERITED_LOCK_ROOTS_ENV] = (
                f"{os.getpid()}={os.path.realpath(mirror_root)}"
            )
            real_cmd = [sys.executable, str(_round._PUBLISH), joined, "--no-commit"]
            if not args.delta:
                real_cmd.append("--no-delta")
            manifest_not_before = time.time()
            real = _round._run(
                real_cmd,
                timeout=_round._PUBLISH_LEG_TIMEOUT_SECS,
                env=real_env,
            )
            print(real.stdout)
            if real.returncode != 0 or "Rows FAILED:" in real.stderr:
                _round._print_step_failure(
                    "publish (all rows)",
                    [sys.executable, str(_round._PUBLISH), joined],
                    real.stderr,
                )
                return _round._EXIT_FAIL

            manifest = _round._read_fresh_round_manifest(
                Path(repo_root), manifest_not_before
            )
            manifest_added = sorted(manifest.added_or_updated) if manifest is not None else []

            with tempfile.TemporaryDirectory() as gate_tmp:
                gate_rc = _run_gate_legs(
                    repo_root, manifest_added, targets, str(percolate_root), Path(gate_tmp)
                )
            if gate_rc is not None:
                return gate_rc

            pathspec = (
                []
                if manifest is None
                else _round._pathspec_from_manifest(manifest, repo_root)[0]
            )

            if not pathspec:
                print(
                    f"percolate-mirror {mirror_root} — publish reported no changed "
                    "files; nothing to commit."
                )
                return _round._EXIT_OK

            if args.yes:
                print(f"Proceed with commit + publish? [y/N] y (--yes)")
            elif args.invocation_authorized:
                print(
                    "Proceed with commit + publish? [y/N] y (--invocation-authorized)"
                )
            elif sys.stdin.isatty():
                answer = input(
                    f"Proceed with commit + publish of {len(pathspec)} file(s)? [y/N] "
                ).strip().lower()
                if answer not in ("y", "yes"):
                    print("Publish cancelled.")
                    return _round._EXIT_OK
            else:
                print(
                    "Confirm required, no tty and no --invocation-authorized.",
                    file=sys.stderr,
                )
                return _round._EXIT_CONFIRM_REQUIRED

            subject = (
                f"percolate publish: {Path(mirror_root).name} "
                f"({len(targets)} row(s), {len(pathspec)} file(s))"
                f"{_round._source_sha_suffix()}"
            )
            print(f"=== percolate-mirror {mirror_root} — commit ({len(pathspec)} file(s)) ===")
            # `_round._SCOPED_GIT_COMMIT` went with it, so this leg raised
            from functools import partial  # noqa: PLC0415

            from coordinator_core.git.commit import (  # noqa: PLC0415
                CommitRefused,
                FilterUnsupported,
                commit_paths,
                hash_worktree_blobs_via_spawn,
            )
            from coordinator_core.ops.ceremony.commit_message import (  # noqa: PLC0415
                compose_message,
            )

            try:
                outcome = commit_paths(
                    repo_root,
                    pathspec,
                    compose_message(subject=subject),
                    blob_fallback=partial(hash_worktree_blobs_via_spawn, cwd=repo_root),
                )
            except (CommitRefused, FilterUnsupported) as exc:
                _round._print_step_failure(
                    "commit (ceremony.commit_v2)",
                    ["commit_paths"],
                    str(exc),
                )
                return _round._EXIT_FAIL
            sha = outcome.sha
            print(f"percolate-mirror {mirror_root} — commit {sha[:12]}")

            if args.no_publish:
                print("")
                print(f"percolate-mirror {mirror_root} — committed, push skipped (--no-publish).")
                return _round._EXIT_OK

            push = _round._push_dest(repo_root)
            if push.returncode != 0:
                print("percolate-mirror: push failed:", file=sys.stderr)
                print(push.stderr.strip(), file=sys.stderr)
                return _round._EXIT_FAIL

            print("")
            print(f"percolate-mirror {mirror_root} — PASS")
            print(f"  rows:      {len(targets)} in one publish invocation")
            print(f"  committed: {len(pathspec)} file(s)")
            print(f"  pushed:    {repo_root}")
            return _round._EXIT_OK
    except _round._RoundLockTimeout as exc:
        from percolate.wire_contract import lock_busy_message  # noqa: PLC0415 - engine bound by _bootstrap_engine() above

        print(
            f"percolate-mirror: {lock_busy_message(repo_root, exc)}",
            file=sys.stderr,
        )
        return _round._EXIT_LOCK_BUSY


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
