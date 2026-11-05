"""group-em-home: resolve, seed, migrate, and inspect the machine-local G-EM home.

Verbs: `path`, `ensure`, `holder`, `migrate`, `sync [--push]`, `prune`; `--json` on each. Exit 3 on a
refused home (prints the conflicting checkout), exit 4 when `migrate` cannot move the legacy home,
exit 5 on `sync: conflict` (paths on stderr). No remote is exit 0 with a warning. Authored in
Claude-klabauter; DoE consumes it.
"""
import argparse
import json
import os
import sys

_HOLDER_FIELDS = ("session_id", "peer_name", "repo_root", "nominated_at", "live")
_REFUSAL_TOKEN = "A-GROUP-EM-HOME-INSIDE-A-CHECKOUT-IS-REFUSED-NOT-MOVED"
_SYNC_CONFLICT_EXIT = 5
_OK_OUTCOMES = ("moved", "no-legacy", "configured")


def _blocked_text(outcome: str, legacy: str, target: str) -> str:
    return {
        "both-present": f"both {legacy} and {target} exist; nothing was moved or merged",
        "live": f"{legacy} is in use by a live session or G-EM; retry when none is running there",
        "busy": f"{legacy} could not be renamed (the OS refused); retry when nothing holds it open",
    }.get(outcome, "")


def _place_engine_on_path() -> str:
    """Resolve the engine root through the claude-klabauter bin resolver and put it on `sys.path`."""
    lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    from engine_bootstrap import _resolve_engine_root

    root = _resolve_engine_root(os.path.abspath(__file__))
    if not root:
        raise RuntimeError("engine root unresolved")
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def _create_remote(gem_home, home, report: dict) -> None:
    """`gh repo create --private` from the home and record the URL and branch machine-locally.
    A failure leaves the report's opt-out untouched."""
    import shutil
    import subprocess

    from coordinator_core import machine_resolver
    from coordinator_core.git.run import run_git

    if not shutil.which("gh"):
        return
    res = subprocess.run(
        ["gh", "repo", "create", "group-em-home", "--private", "--source", str(home), "--remote", "origin"],
        capture_output=True, text=True, timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if res.returncode != 0:
        print(f"group-em-home: gh repo create failed: {(res.stderr or res.stdout).strip()}", file=sys.stderr)
        return
    url = run_git(["remote", "get-url", "origin"], cwd=str(home)).stdout.strip()
    if not url:
        return
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(home)).stdout.strip()
    machine_resolver.registry_set(gem_home.REMOTE_URL_KEY, url)
    machine_resolver.registry_set(
        gem_home.REMOTE_BRANCH_KEY, branch if branch and branch != "HEAD" else gem_home.DEFAULT_REMOTE_BRANCH
    )
    report["remote"], report["remote_opt_out"] = url, None


def _ensure_tail(gem_home, report: dict, args) -> int:
    """Create the remote on request, install the path guard, run the entry pull, print."""
    from coordinator_core.group_em import gem_home_path_guard, gem_home_sync

    home = report["home"]
    if args.create_remote and not report["remote"]:
        _create_remote(gem_home, home, report)
    gem_home_path_guard.install(home)
    sync = gem_home_sync.pull_on_entry(home)
    report["sync"] = sync
    if not report["remote"]:
        print(f"group-em-home: no remote ({report['remote_opt_out']}); home is local-only", file=sys.stderr)
    if sync["sync"] == "conflict":
        print("group-em-home: sync: conflict: " + ", ".join(sync["paths"]), file=sys.stderr)
    out = dict(report)
    out["home"] = str(home)
    print(json.dumps(out) if args.json else str(home))
    return _SYNC_CONFLICT_EXIT if sync["sync"] == "conflict" else 0


def _sync_or_prune(args, home) -> int:
    from coordinator_core.group_em import gem_home_prune, gem_home_sync

    if args.verb == "prune":
        print(json.dumps(gem_home_prune.prune(home, fix_paths=args.fix_paths), default=str))
        return 0
    if args.push:
        rep = gem_home_sync.push_leg(home, "group-em-home: sync")
    else:
        rep = gem_home_sync.pull_on_entry(home)
    print(json.dumps({"home": str(home), **rep}))
    if rep["sync"] == "conflict":
        print("group-em-home: sync: conflict: " + ", ".join(rep["paths"]), file=sys.stderr)
        return _SYNC_CONFLICT_EXIT
    return 0


def main(argv=None) -> int:
    try:
        _place_engine_on_path()
        from coordinator_core.group_em import gem_home as _gem_home
    except Exception as exc:
        print(f"group-em-home: engine gem_home unresolvable: {exc}", file=sys.stderr)
        return 2

    ap = argparse.ArgumentParser(prog="group-em-home")
    ap.add_argument("verb", choices=("path", "ensure", "holder", "migrate", "sync", "prune"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--push", action="store_true", help="sync: commit, pull --rebase, push (default: entry pull)")
    ap.add_argument(
        "--fix-paths", action="store_true",
        help="prune: also rewrite concrete path citations in the home's markdown (fix-concrete-path-citations --apply)",
    )
    ap.add_argument(
        "--create-remote", action="store_true",
        help="ensure: when no remote is recorded, `gh repo create --private` and record its keys",
    )
    ap.add_argument(
        "--refresh",
        action="store_true",
        help=f"ensure: rewrite CLAUDE.md from the template; migrate: the same, only when a "
        f"{_gem_home.LEGACY_DIRNAME} home moved",
    )
    args = ap.parse_args(argv)
    outcome = None
    seed = None
    try:
        if args.verb == "migrate":
            outcome = _gem_home.migrate_legacy_home()
            if outcome == "moved" and args.refresh:
                home, seed = _gem_home.ensure_home_outcome(refresh=True)
            else:
                home = _gem_home.resolve_home()
        elif args.verb == "ensure":
            report = _gem_home.ensure_home_report(refresh=args.refresh)
            home, seed = report["home"], report["seed"]
        else:
            home = _gem_home.resolve_home()
    except _gem_home.HomeRefused as exc:
        print(f"group-em-home: refused: {exc.home} is inside a checkout ({_REFUSAL_TOKEN})", file=sys.stderr)
        print(exc.checkout)
        return 3
    if seed == "no-template":
        print("group-em-home: no CLAUDE.md seed template resolved; set CLAUDE_PLUGIN_ROOT or "
              "machine-local repos.content_root", file=sys.stderr)
    if args.verb == "ensure":
        return _ensure_tail(_gem_home, report, args)
    if args.verb in ("sync", "prune"):
        return _sync_or_prune(args, home)
    if args.verb == "holder":
        rec = _gem_home.gem_holder()
        holder = {k: rec.get(k) for k in _HOLDER_FIELDS} if rec else None
        if args.json:
            print(json.dumps({"home": str(home), "holder": holder}))
        else:
            print(json.dumps(holder) if holder else "no live G-EM")
        return 0
    if args.verb == "migrate":
        if outcome == "refused":
            # The target (not the resolved legacy home) lands in a checkout.
            print(f"group-em-home: refused: the {_gem_home.DEFAULT_DIRNAME} target is inside a checkout "
                  f"({_REFUSAL_TOKEN})", file=sys.stderr)
            return 3
        if args.json:
            print(json.dumps({"outcome": outcome, "home": str(home)}))
        else:
            print(outcome)
            base = home.parent
            why = _blocked_text(
                outcome, str(base / _gem_home.LEGACY_DIRNAME), str(base / _gem_home.DEFAULT_DIRNAME)
            )
            if why:
                print(why)
        return 0 if outcome in _OK_OUTCOMES else 4
    print(json.dumps({"home": str(home)}) if args.json else str(home))
    return 0


if __name__ == "__main__":
    sys.exit(main())
