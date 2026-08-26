"""
regenerate-orientation-cache — CLI trampoline over claude-klabauter
coordinator_core.orientation.regenerate_cache.

Single source-of-truth derivation for state/orientation_cache.md.

Spec backlink: docs/plans/2026-05-18-orientation-cache-authoring-discipline.md
Schema: plugins/coordinator/pipelines/workday-start-internals.md § 5.5
Verifier: plugins/coordinator/bin/verify-orientation-cache-sync.py
Recipe: scratch/subagent-sandbox/bash-to-python-engine-migration/recipe-t3a-g3.md § 2

Usage:
  regenerate-orientation-cache --invoker <workday-start|update-docs|workstream-complete|handoff|quick-wrap|sweep-boot>
  regenerate-orientation-cache --invoker <slug> --check       Print to stdout, don't write

Writer tiers:
  ceremony    (workday-start, update-docs)             — full regen, clears pinboard
  mid-session (workstream-complete, handoff,            — re-derives all sections from disk (same
               quick-wrap, sweep-boot)                    as ceremony); preserves existing pinboard
                                                          slot unless --pinboard supplied.
                                                          sweep-boot is a MACHINE invoker (fired by
                                                          the async sweep-boot SessionStart hook on a
                                                          detected-stale cache), not a ceremony a human
                                                          runs — otherwise identical mid-session tier.
                                                          quick-wrap closes a SESSION, not the day, so
                                                          it preserves the day-scoped pinboard the way
                                                          its siblings do — /workday-complete is the
                                                          day-level close that clears it.

Mid-session pinboard writes:
  regenerate-orientation-cache --invoker workstream-complete --pinboard "<one-line note>"
  (overwrites the single pinboard slot; pass --pinboard "" to clear)
  This is a FULL regen (every section re-derived from disk) that happens to
  also set the pinboard — kept unchanged, byte-identically, for existing
  callers. See --pinboard-only below for the fast path.

Mid-session pinboard-ONLY writes (fast path — ADDITIVE, does not replace --pinboard above):
  regenerate-orientation-cache --invoker workstream-complete --pinboard-only "<one-line note>"
  (patches ONLY the pinboard line in place; zero re-derive of any other
  section — no git spawns, no *.uproject find, no tasks/ globs. Requires an
  existing cache file — i.e. at least one prior full regen. mid-session
  invokers only (workstream-complete, handoff); ceremony invokers must clear
  the pinboard via a full regen, not this path. --pinboard-only "" clears.)

Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
for this shape. On Windows, this file's co-located `.cmd` twin wins via
`PATHEXT` when invoked as a bareword, so the shebang is never read there; on
macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
via the extensionless name or a resolved-interpreter prefix, never a bareword
`.py` through git-bash — git-bash DOES honor the shebang and would exec-127
with no `python3` present. See the carve-out in DoE-claude's
coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
this wiki lives in the DoE-claude repo, not here).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import require_dispatch_engine_on_path  # noqa: E402

_VALID_INVOKERS = (
    "workday-start", "update-docs", "workstream-complete", "handoff", "quick-wrap", "sweep-boot",
)


def _import_orientation_module():
    """Resolve the engine root, put it on sys.path, and import the ported module.

    Reuses cc_invoke's battle-tested engine-root resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) — this is a plain
    in-process import, not an RPC invoke, so cc_invoke's subprocess-spawn
    transport (cc_invoke()/route()) is deliberately NOT used here (same shape
    as `normalize-snippet`, per the recipe's explicit disposition for this script).
    """
    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.orientation import regenerate_cache as mod

    return mod


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="regenerate-orientation-cache",
        description="Regenerate state/orientation_cache.md.",
    )
    parser.add_argument("--invoker", required=True, choices=_VALID_INVOKERS)
    parser.add_argument("--check", action="store_true", help="Print to stdout, don't write.")
    parser.add_argument(
        "--pinboard",
        default=None,
        help='Mid-session-tier pinboard note override (pass "" to clear). Full regen.',
    )
    parser.add_argument(
        "--pinboard-only",
        default=None,
        metavar="NOTE",
        help=(
            'Fast-path pinboard patch (pass "" to clear) — zero section re-derive. '
            "Requires an existing cache file; mid-session invokers only."
        ),
    )
    args = parser.parse_args()

    if args.pinboard_only is not None and args.pinboard is not None:
        print("ERROR: --pinboard and --pinboard-only are mutually exclusive", file=sys.stderr)
        sys.exit(2)

    try:
        mod = _import_orientation_module()
    except RuntimeError as exc:
        print(f"regenerate-orientation-cache: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except ImportError as exc:
        print(
            f"regenerate-orientation-cache: coordinator_core.orientation.regenerate_cache "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = mod.resolve_repo_root(Path.cwd())

    if args.pinboard_only is not None:
        # sweep-boot is deliberately NOT admitted here even though it shares the
        # mid-session tier with workstream-complete/handoff: the async self-heal
        # always does a FULL regen (it is re-deriving a cache it just found stale,
        # not patching a single pinboard line), so --pinboard-only has no caller on
        # this invoker. Do not "fix" this to look like an oversight.
        if args.invoker not in ("workstream-complete", "handoff"):
            print(
                "ERROR: --pinboard-only is a mid-session fast path; invoker must be "
                "workstream-complete or handoff (got "
                f"{args.invoker!r}) — ceremony invokers clear the pinboard via a full regen.",
                file=sys.stderr,
            )
            sys.exit(2)
        cache_file = mod.resolve_cache_file(repo_root)
        try:
            output = mod.patch_pinboard_only(cache_file, args.pinboard_only, check=args.check)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(2)
        except TimeoutError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        if args.check:
            sys.stdout.write(output)
        else:
            print(
                f"regenerate-orientation-cache: patched pinboard-only in {cache_file} "
                f"(invoker={args.invoker}, tier=pinboard-only)",
                file=sys.stderr,
            )
        return

    pinboard_set = args.pinboard is not None

    try:
        result = mod.build_cache(
            invoker=args.invoker,
            repo_root=repo_root,
            pinboard=args.pinboard,
            pinboard_set=pinboard_set,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    if result["skipped"]:
        print(result["reason"], file=sys.stderr)
        sys.exit(0)

    if args.check:
        sys.stdout.write(result["output"])
    else:
        mod.write_cache(result["cache_file"], result["output"])
        mod.clear_failures_log(str(repo_root))
        print(
            f"regenerate-orientation-cache: wrote {result['cache_file']} "
            f"(invoker={args.invoker}, tier={result['tier']})",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
