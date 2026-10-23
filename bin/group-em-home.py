"""group-em-home: resolve, seed, migrate, and inspect the machine-local G-EM home.

Verbs: `path`, `ensure`, `holder`, `migrate`; `--json` on each. Exit 3 on a refused home
(prints the conflicting checkout), exit 4 when `migrate` cannot move the legacy home. Authored in
Claude-klabauter; DoE consumes it.
"""
import argparse
import json
import os
import sys

_HOLDER_FIELDS = ("session_id", "peer_name", "repo_root", "nominated_at", "live")
_REFUSAL_TOKEN = "A-GROUP-EM-HOME-INSIDE-A-CHECKOUT-IS-REFUSED-NOT-MOVED"
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


def main(argv=None) -> int:
    try:
        _place_engine_on_path()
        from coordinator_core.group_em import gem_home as _gem_home
    except Exception as exc:
        print(f"group-em-home: engine gem_home unresolvable: {exc}", file=sys.stderr)
        return 2

    ap = argparse.ArgumentParser(prog="group-em-home")
    ap.add_argument("verb", choices=("path", "ensure", "holder", "migrate"))
    ap.add_argument("--json", action="store_true")
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
            home, seed = _gem_home.ensure_home_outcome(refresh=args.refresh)
        else:
            home = _gem_home.resolve_home()
    except _gem_home.HomeRefused as exc:
        print(f"group-em-home: refused: {exc.home} is inside a checkout ({_REFUSAL_TOKEN})", file=sys.stderr)
        print(exc.checkout)
        return 3
    if seed == "no-template":
        print("group-em-home: no CLAUDE.md seed template resolved; set CLAUDE_PLUGIN_ROOT or "
              "machine-local repos.content_root", file=sys.stderr)
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
