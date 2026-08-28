#!/usr/bin/env python3
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
`_resolve_repo_root`, `_round_held_lock`, `_split_stdout_by_row_dest`,
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
    """`percolate-round.py`'s helpers, loaded by path. Reused rather than
    re-derived so this entry point can never drift from the round's own
    lock/pre-flight/pathspec semantics."""
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    spec = importlib.util.spec_from_file_location(
        "percolate_round", _BIN_DIR / "percolate-round.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def __getattr__(name: str):
    """PEP 562 module `__getattr__` -- lets a caller that reaches for
    `<this module>._round` / `.publish_lane` BEFORE `main()` has run (e.g.
    this file's own test suite, which monkeypatches `_mod._round`'s
    attributes ahead of calling `_mod.main()`) trigger `_bootstrap_engine()`
    lazily on first access, instead of requiring `_round`/`publish_lane` to
    already be module globals at import time. Only fires when the name is
    NOT already present in this module's `__dict__` -- once
    `_bootstrap_engine()` has run once (via this hook or via `main()`), the
    plain global wins on every later lookup and this function is not called
    again for that name."""
    if name in ("_round", "publish_lane"):
        _bootstrap_engine()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _bootstrap_engine() -> None:
    """Resolve the engine root and bind `_round`/`publish_lane` module
    globals. Called once, first thing in `main()` (or lazily via
    `__getattr__` above, for a caller that reaches for `_round`/
    `publish_lane` before `main()` runs).

    The engine root is put on `sys.path` EXPLICITLY here, not inherited from
    `_load_round_module()` below. That call does happen to leave the engine
    reachable — `percolate-round.py` inserts `coordinator/lib` at its own import
    time — but depending on it made this file's bootstrap an undeclared
    side effect of a sibling's import order: reorder or slim that sibling and
    this import dies with `ModuleNotFoundError: coordinator_core` on the
    published mirror, with nothing here naming the dependency. Declaring it is
    the same seam ~175 other CLIs under this directory already use.

    MUST run before `_load_round_module()` executes below: `percolate-round.py`
    binds `coordinator_core` at ITS OWN module level off a bare self-location
    `sys.path` insert (no `require_dispatch_engine_on_path()` call of its own,
    no LOCATOR-axis bootstrap) — once that exec_module() call runs, whatever
    root it happened to bind wins, and no later `sys.path` insert here can
    rebind an already-imported package.
    NOTE `_BIN_DIR / "lib"`, not `_LIB_DIR` — this file's `_LIB_DIR` is
    `coordinator/lib` (the percolate helpers), while `cc_invoke` lives in
    `coordinator/bin/lib`. They are different directories.
    """
    global _round, publish_lane

    if "_round" in globals():
        # Already bootstrapped (via `main()` or a prior `__getattr__` hit) --
        # re-running would call `_load_round_module()` again and rebind
        # `_round` to a BRAND NEW module object (`importlib.util.module_
        # from_spec` + `exec_module` builds a fresh module every call), which
        # would silently orphan any monkeypatch a caller already applied to
        # the first-bootstrapped `_round`. Idempotent by construction.
        return

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    require_dispatch_engine_on_path()
    # LOAD-BEARING, NOT DEAD. Do not delete on an unused-import sweep: this line is
    # what BINDS coordinator_core, and binding it HERE is the whole fix.
    # require_dispatch_engine_on_path() above only mutates sys.path -- it imports
    # nothing. Without this line the next import below (a binder module
    # that resolves on the LOCATOR axis) wins the race and binds coordinator_core off
    # the working tree instead of the dispatch root, and no later sys.path insert can
    # rebind an already-imported package. Removing it restores a silent wrong-tree
    # divergence that require_dispatch_engine_on_path now raises on.
    # Why: docs/plans/2026-08-26-the-seam-reports-what-it-got.md C9,
    # docs/research/engine-provenance-carrier-dependence.md
    import coordinator_core  # noqa: F401

    _round = _load_round_module()

    from coordinator_core import publish_lane as _publish_lane  # type: ignore[import-not-found]

    publish_lane = _publish_lane


def _mirror_groups(percolate_root: str) -> Dict[str, List[str]]:
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
    from percolate.targets import TargetsError, load_targets  # noqa: E402

    setup_dir = Path(percolate_root) / "setup"
    try:
        rows = load_targets(setup_dir, target_filter=None)
    except TargetsError as exc:
        print(exc.message, file=sys.stderr)
        return {}

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
    """`{target: (source_dir, dest)}` straight off the resolved targets table
    (fields 2 and 3). The gate legs need both per row and must not re-derive
    them through Branch 0, which answers a different question (is this target
    set up for a standalone round) and fails on rows only ever published as
    part of a mirror's set."""
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
    """Resolve `selector` to exactly one mirror worktree root. Accepts the root
    path itself, its basename in either separator form (`claude-klabauter` /
    `claude_klabauter`), or any registered target name landing in it — a caller
    who knows only a row name should not have to learn the path."""
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
    real_stdout: str, targets: List[str], percolate_root: str, tmp: Path
) -> Optional[int]:
    """Steps 2 and 2b — the content-leak scan and the inverse-drift check —
    run against the real run's own output. Returns an exit code to return, or
    `None` when every leg passed.

    These are the reason a publish to a PUBLIC mirror is allowed to land at
    all: `scan-secrets` exit 2 is a HIGH-tier credential shape and aborts
    before any commit, and `inverse-drift` surfaces commits authored directly
    in dest that this publish is about to overwrite. Omitting them (as this
    module did when first written) makes the entry point cheaper than
    `percolate-round` by removing the safety, not the cost.

    Scanned per target, each over ITS OWN row's file list. `scan-secrets` is
    target-scoped (peer-repo pattern, `registry_codenames` guard), so a row
    needs its own pass — and must not be handed another row's sources, which
    would judge them under the wrong ruleset. An earlier revision fed every
    row the whole run's list on an "over-inclusive is safe" reading; that is
    wrong in this direction, and the failure is recorded at the call site.
    """
    # Per-row stdout, keyed by that row's own reported `Target:` line. Each
    # row's scan list must come from ITS OWN chunk: `scan-secrets` is
    # target-scoped (peer-repo pattern, `registry_codenames` guard), so feeding
    # it the whole run's file list judges every other row's sources under this
    # row's ruleset. Observed live 2026-08-18: doing that raised HIGH-tier
    # "credential" hits on ordinary prose in `docs/install/` and `scripts/`
    # while scanning under `claude-klabauter-coordinator-bin`, blocking a clean
    # 9/9 publish. Over-inclusive is NOT the safe direction here — it
    # manufactures false blocks, and a HIGH tier that fires on documentation is
    # one operators learn to route around.
    row_chunks = {
        dest: chunk
        for dest, chunk in _round._split_stdout_by_row_dest(real_stdout, "")
    }

    identity_file = Path(percolate_root) / "setup" / ".percolate-identity"
    peer_repos_file = _round._resolve_central_state()
    medium_total = 0
    crlf_dismissed = 0
    unreliable_anchor: List[tuple] = []
    real_drift: List[tuple] = []

    row_paths = _row_paths(percolate_root)
    for target in targets:
        # Source/dest come from the resolved targets table, NOT `_branch0_gate`.
        # Branch 0 is a per-target FIRST-RUN SETUP check (it fails
        # MISSING_IGNORE on a row with no `.percolate-ignore` of its own).
        # `percolate-round` runs it once, for the single target its caller
        # named and therefore set up. Running it across every row of a mirror
        # fails on rows that are only ever published as part of the set —
        # observed live 2026-08-18 on `claude-klabauter-toplevel-reference`,
        # which aborted the gate legs AFTER a clean 9/9 publish and left the
        # dest synced but uncommitted.
        paths = row_paths.get(target)
        if paths is None:
            print(
                f"percolate-mirror: '{target}' is not in the resolved targets "
                "table; cannot run its gate legs.",
                file=sys.stderr,
            )
            return _round._EXIT_FAIL
        source_dir, dest = paths

        row_stdout = row_chunks.get(dest)
        if row_stdout is None:
            # publish.py reported no `Target:` line for this row — it touched
            # nothing this run, so it has nothing of its own to scan.
            continue
        row_stdout_path = tmp / f"row-stdout-{targets.index(target)}.txt"
        row_stdout_path.write_text(row_stdout, encoding="utf-8", newline="\n")

        parse = _round._run(
            [
                sys.executable,
                str(_round._PARSE_DRYRUN),
                "parse-dryrun",
                "--stdout-file",
                str(row_stdout_path),
                "--source-dir",
                source_dir,
            ],
            timeout=_round._ROUND_SCAN_LEG_TIMEOUT_SECS,
        )
        if parse.returncode != 0:
            _round._print_step_failure("percolate-parse-dryrun", [], parse.stderr)
            return _round._EXIT_FAIL
        try:
            scan_file_list = json.loads(parse.stdout)["preflight"][
                "step2c_scan_file_list"
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            _round._print_step_failure(
                "percolate-parse-dryrun — malformed envelope",
                [],
                f"{type(exc).__name__}: {exc}",
            )
            return _round._EXIT_FAIL

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
            "`repos.claude_klabauter`), its bare name "
            "(claude-klabauter), or any registered target name landing in it."
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

    # Declared here and not inherited from `percolate-round`: this module imports that
    # one by path for its helpers and never calls its `main()`, so the round's own
    # declaration does not run for a mirror publish — and this driver spawns
    # `scoped-git-commit` itself (`_commit_mirror`), which is the one leg the lane
    # exists for. PM ruling 2026-08-21, DR-350; mechanism in
    # `coordinator_core.publish_lane`.
    publish_lane.declare_lane()

    args = _build_parser().parse_args(argv)

    # `_resolve_percolate_root` owns the override precedence itself (it returns
    # `override` unchanged when truthy), so the override is passed IN rather than
    # short-circuited around with `or` — the latter called it with no argument on
    # the no-override path, which is a TypeError, not a fallback.
    percolate_root = _round._resolve_percolate_root(args.percolate_root)
    if not percolate_root:
        print("percolate-mirror: could not resolve PERCOLATE_ROOT.", file=sys.stderr)
        return _round._EXIT_USAGE

    groups = _mirror_groups(str(percolate_root))
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
            timeout=_round._round_lock_wait_secs(),
        ):
            # The destination-dirtiness preflight is GONE (plan AC5). It existed
            # only because a stdout-derived pathspec could not tell this round's
            # bytes from a crashed predecessor's; the manifest read below names
            # them, and its freshness check does the job the preflight did.
            print(f"=== percolate-mirror {mirror_root} — publish ({len(targets)} rows, one invocation) ===")
            # Inherited-holder handoff. This process already holds the dest
            # lock, and `publish.py::main` acquires the SAME key
            # (`held_lock`'s `sha1(realpath(target))`) for every row's resolved
            # root — without this token the child contends against its own
            # parent and FATALs on a lock it can never win. The token names
            # THIS process's pid (the child's direct parent) and the root this
            # frame holds, and is scoped to the child's own env, never the
            # ambient one.
            real_env = dict(os.environ)
            real_env[_round._INHERITED_LOCK_ROOTS_ENV] = (
                f"{os.getpid()}={os.path.realpath(mirror_root)}"
            )
            real_cmd = [sys.executable, str(_round._PUBLISH), joined]
            if not args.delta:
                # publish.py defaults delta ON (PM ruling 2026-08-19) — the
                # engine owns that, not each caller. Only an explicit opt-out
                # is forwarded.
                real_cmd.append("--no-delta")
            # Stamped BEFORE the run so `_read_fresh_round_manifest` can reject a
            # manifest this round did not write (a crashed predecessor's, or a
            # prior round's leftover when this one is a no-op).
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

            with tempfile.TemporaryDirectory() as gate_tmp:
                gate_rc = _run_gate_legs(
                    real.stdout, targets, str(percolate_root), Path(gate_tmp)
                )
            if gate_rc is not None:
                return gate_rc

            # The commit pathspec comes from the manifest publish.py persisted,
            # never from parsing its printed NEW:/UPDATE:/REMOVE: lines. Same fix
            # as percolate-round.py's `_cmd_round_default`; this file carried a
            # structurally identical copy of that defect.
            manifest = _round._read_fresh_round_manifest(
                Path(repo_root), manifest_not_before
            )
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
            )
            print(f"=== percolate-mirror {mirror_root} — commit ({len(pathspec)} file(s)) ===")
            # `ceremony.scoped_git_commit` was KILLED 2026-08-23 (DR-344) and
            # `_round._SCOPED_GIT_COMMIT` went with it, so this leg raised
            # AttributeError the moment it was reached -- dead from the day of the
            # kill, and invisible because the tests above it never got past
            # "nothing to commit". Routed onto the same in-process seam
            # percolate-round's own commit leg uses (§ C6, 2026-08-25).
            import uuid  # noqa: PLC0415 - lazy, matching percolate-round's own commit leg
            from coordinator_core.ops.ceremony import commit_pipeline  # noqa: PLC0415

            pipeline_result = commit_pipeline.run_commit_pipeline(
                repo_root,
                session_id=f"percolate-mirror-{uuid.uuid4().hex}",
                subject=subject,
                stage_paths=pathspec,
                caller_paths=set(pathspec),
                push_mode=commit_pipeline.PUSH_MODE_NEVER,
            )
            committed = (
                pipeline_result.committed_sha is not None or pipeline_result.sha_unverified
            )
            if not committed:
                _round._print_step_failure(
                    "commit (ceremony.commit)",
                    ["run_commit_pipeline"],
                    pipeline_result.reason or "commit did not land",
                )
                return _round._EXIT_FAIL
            sha = pipeline_result.committed_sha or "(sha unverified)"
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
        print(
            f"percolate-mirror: {_round._lock_busy_message(repo_root, exc)}",
            file=sys.stderr,
        )
        return _round._EXIT_LOCK_BUSY


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
