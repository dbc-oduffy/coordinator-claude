#!/usr/bin/env python3
"""coordinator/bin/coordinator-publish.py — namespaced canonical alias for
`coordinator/bin/publish.py` (the percolate publish driver).

Why this file exists: `publish` is/was the only bare generic verb among the
installed forwarder set (see `docs/plans/2026-07-25-posix-bareword-path-provisioning.md`
task D1 — deferred there pending PM ratification, since ratified). `<settings-home>/bin` went
onto PATH 2026-07-26 (commit 96708025), turning a theoretical bareword collision into a live
one. Every other generic verb (`check`/`run`/`build`/`validate`/`setup`/`doctor`) only ever appears as a
compound-prefixed name (`publish-resolve-target`, `publish-time-transform-py`, etc.) — `publish`
was the sole exception. This file installs `coordinator-publish` (+ its generated `.cmd` twin) as
the namespaced canonical name, matching the fleet's existing `coordinator-*` prefix convention
(`coordinator-doc-new`, `coordinator-lesson-add`, `coordinator-queue-append`).

`publish` itself is INTENTIONALLY still installed and untouched — this is an additive rename,
not a cutover. `coordinator/skills/percolate/SKILL.md` (coordinator-content-repo) invokes the bareword
`"${COORDINATOR_SETTINGS_HOME:-...}/bin/publish"` today; deleting `publish` here would break that
skill immediately. Deleting the old name is a separate, gated follow-up once callers have
actually moved to `coordinator-publish` — see the D1 dispatch report for the caller list.

Delegates by `runpy`-executing `publish.py` in this same directory as `__main__`, rather than
importing and re-calling its `main()`, so this alias never drifts from `publish.py`'s own
`sys.argv`/`sys.exit` contract and carries zero duplicated dispatch logic — `publish.py` remains
the SOLE owner of the percolate publish driver's behavior; this file is purely a namespaced
second name for the same on-disk artifact.

Negative-spec: do NOT reimplement or re-import `publish.py`'s `main()` here and call it directly
— that would fork argv/exit-code handling into a second implementation the moment either file's
signature changes. `runpy.run_path(..., run_name="__main__")` re-executes the target module's own
`if __name__ == "__main__":` block verbatim, so this alias is always byte-identical in behavior to
invoking `publish.py` directly.

The hand-off target is a commit clone of this tree at the round's commit
(`lib/commit_clone.py`), never the live working tree; an invoking checkout that carries its own
`publish.py` is still honoured.

The other addition: before the hand-off, a default klabauter publish is refused when its source
lacks the live publish's source head (`--allow-source-rollback` admits a deliberate rollback;
the flag is consumed here and never reaches `publish.py`).
"""

import argparse
import importlib
import importlib.util
import runpy
import subprocess
import sys
from pathlib import Path


def _invoking_clone_bin(own_bin: Path) -> Path | None:
    """The `coordinator/bin` of the nearest checkout enclosing cwd that carries its own
    `publish.py`, or None when that is this file's own tree. Walks parents for `.git`
    (no git spawn): a publish round pins `coordinator_core` to the clone it was launched
    from, so the driver must come from that same clone."""
    try:
        here = Path.cwd().resolve()
    except OSError:
        return None
    for root in (here, *here.parents):
        if (root / ".git").exists():
            clone_bin = root / "coordinator" / "bin"
            if (clone_bin / "publish.py").is_file() and clone_bin != own_bin:
                return clone_bin
            return None
    return None


_ALLOW_ROLLBACK_FLAG = "--allow-source-rollback"


def _engine_root() -> str:
    """The resolved engine checkout (never this file's own tree); raises when no rung resolves."""
    lib = str(Path(__file__).resolve().parent / "lib")
    sys.path.insert(0, lib)
    try:
        import cc_invoke

        return cc_invoke.resolve_engine_root(__file__)
    finally:
        try:
            sys.path.remove(lib)
        except ValueError:
            pass


def _parse_guard_args(argv: list[str]) -> argparse.Namespace:
    """The few `publish.py` arguments the regression guard reads. Value-taking flags are
    declared so a flag's value is never mistaken for the target."""
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    ap.add_argument("target", nargs="?", default="")
    ap.add_argument("--dry-run", action="store_true")
    for flag in (
        "--commit", "--source-ref", "--withheld-paths-json", "--progress-file", "--percolate-root",
        "--dest-root-override", "--dest-root-live",
    ):
        ap.add_argument(flag, default=None)
    ap.add_argument("--swap-over-mid-stage-runs", default=None)
    return ap.parse_known_args(argv[1:])[0]


def _regression_refusal(argv: list[str], source_root: Path) -> str | None:
    """Refusal text when this default publish ships a source lacking the live klabauter
    publish's source head, else None. Runs from this file's own tree before any hand-off, so
    an older invoking clone's `publish.py` cannot skip it. Admits (with a stderr note) when it cannot judge."""
    args = _parse_guard_args(argv)
    if args.dry_run or (args.target and "klabauter" not in args.target):
        return None
    preloaded = set(sys.modules)
    own_root = ""
    try:
        # `sys.path[0]` is `coordinator/bin`; the resolved engine root is what makes the import work off PYTHONPATH.
        own_root = _engine_root()
        sys.path.insert(0, own_root)
        # Dynamic on purpose: a static import would make the allowlist's import walk derive this
        # driver as shippable to a mirror that withholds `coordinator_core`.
        _settings_home = importlib.import_module("coordinator_core._settings_home")
        registry_get = importlib.import_module("coordinator_core.machine_resolver").registry_get
        check_publish_source_regression = importlib.import_module(
            "coordinator_core.percolate.source_preflight"
        ).check_publish_source_regression

        mirror = registry_get("repos.claude_klabauter")
        if not mirror:
            return None
        try:
            provenance = _settings_home.settings_home() / "machine-local" / "publish-provenance.json"
        except Exception:
            provenance = None
        return check_publish_source_regression(
            source_root,
            Path(mirror),
            source_ref=args.commit or args.source_ref or "",
            provenance_path=provenance,
        )
    except Exception as _exc:
        print(f"coordinator-publish: source-regression guard unjudgeable: {type(_exc).__name__}: {_exc}", file=sys.stderr)
        return None
    finally:
        try:
            sys.path.remove(own_root)
        except ValueError:
            pass  # includes own_root == "" (resolution failed before the insert)
        # The invoking clone's driver must import its own coordinator_core, not this tree's.
        for name in [m for m in sys.modules if m not in preloaded and m.split(".")[0] == "coordinator_core"]:
            del sys.modules[name]


class _CloneRefused(RuntimeError):
    """The round's commit clone could not be materialised; the door refuses."""


def _publish_ref_note() -> str:
    return "A published source head is fetchable from origin as refs/heads/publish/<sha>."


def _round_commit_clone_bin(own_bin: Path, argv: list[str]) -> Path | None:
    """`coordinator/bin` of a commit clone of this tree at the round's commit (`--commit`/
    `--source-ref`, else HEAD), or None when this tree is already a clone. Any failure to
    materialise raises `_CloneRefused`: the door never runs the live tree."""
    own_root = own_bin.parents[1]
    ref = "HEAD"
    try:
        spec = importlib.util.spec_from_file_location("_cwp_commit_clone", own_bin / "lib" / "commit_clone.py")
        cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cc)
        if cc.is_commit_clone(own_root):
            return None
        args = _parse_guard_args(argv)
        ref = args.commit or args.source_ref or "HEAD"
        proc = subprocess.run(
            ["git", "-C", str(own_root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        sha = proc.stdout.strip()
        if proc.returncode != 0 or not sha:
            raise RuntimeError(f"{ref!r} does not resolve to a commit in {own_root}")
        clone = cc.materialise_commit_clone(own_root, sha, cc.default_cache_root())
        return clone / "coordinator" / "bin"
    except Exception as _exc:
        _fix = (
            f'python "{own_bin / "lib" / "commit_clone.py"}" materialise <full-sha> --repo "{own_root}"'
            f' (sha: git -C "{own_root}" rev-parse {ref})'
        )
        raise _CloneRefused(
            f"{type(_exc).__name__}: {_exc}; nothing ran from the live tree. Retry: {_fix}"
        ) from _exc


def main(argv: list[str]) -> int:
    _own_bin = Path(__file__).resolve().parent
    _invoking = _invoking_clone_bin(_own_bin)
    try:
        _clone_bin = _invoking or _round_commit_clone_bin(_own_bin, argv)
    except _CloneRefused as _exc:
        print(f"coordinator-publish: refused -- commit clone failed: {_exc}", file=sys.stderr)
        return 1
    _allow_rollback = _ALLOW_ROLLBACK_FLAG in argv
    argv = [a for a in argv if a != _ALLOW_ROLLBACK_FLAG]
    if not _allow_rollback:
        # A commit clone's git lacks the live head's history, so the guard would read "cannot
        # judge" and go silent; this tree holds the same commit with its full ancestry.
        _judge_root = (_invoking or _own_bin).parents[1]
        _refusal = _regression_refusal(argv, _judge_root)
        if _refusal:
            print(f"coordinator-publish: refused: {_refusal} {_publish_ref_note()}", file=sys.stderr)
            return 1
    _run_bin = _clone_bin or _own_bin
    _runner = _run_bin / "lib" / "commit_clone.py"
    if _runner.is_file():
        _spec = importlib.util.spec_from_file_location("_cwp_clone_runner", _runner)
        _cc = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_cc)
        if _cc.is_commit_clone(_run_bin.parents[1]):
            # A commit clone holds only the publisher seed: run_entry_from_clone installs the
            # filler (here and in every child) that writes the rest of the engine from the commit.
            return _cc.run_entry_from_clone(_run_bin.parents[1], "coordinator/bin/publish.py", ["publish.py", *argv[1:]])
    if _clone_bin is not None:
        _own_root = _own_bin.parents[1]
        _drop = {str(_own_bin), str(_own_root)}
        sys.path[:] = [p for p in sys.path if p not in _drop]
        sys.path[:0] = [str(_clone_bin), str(_clone_bin.parents[1])]
    _target = (_clone_bin or _own_bin) / "publish.py"
    argv = list(argv)
    argv[0] = str(_target)
    sys.argv = argv
    try:
        runpy.run_path(str(_target), run_name="__main__")
    except SystemExit as _exc:
        return _exc.code if isinstance(_exc.code, int) else (0 if _exc.code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
