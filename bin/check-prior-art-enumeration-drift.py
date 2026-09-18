#!/usr/bin/env python3
"""check-prior-art-enumeration-drift — flag a describer that re-enumerates the corpus.

WHY THIS EXISTS. The prior-art-checker's recall corpus used to be hand-copied as an itemized
corpus list at describer sites that nobody owned, and the sweep was never complete: the
2026-07-09 and 2026-07-11 corpus additions each left a describer stale.
Both authored sites now carry one durable phrase instead of an itemized list (see
`docs/plans/2026-09-11-prior-art-corpus-de-enumeration-last-sta.md` § Durable phrase). This
guard keys on PRESENCE of that phrase, not absence of the old seed: the old seed's only live
occurrences were deleted by that same plan, so an absence scan would match nothing but its own
self-quotations. Presence at the two named sites is the condition a future edit can actually
break — re-enumerating either site removes the phrase and this guard names the file.

Zero-spawn: stdlib only, no subprocess, no shell.

PATH RESOLUTION — DOCTRINE ASSET. Both sites (`docs/wiki/reviewer-pipeline.md`,
`snippets/prior-art-check-consumption.md`) are DoE-claude doctrine assets published under the
plugin root, not `Path(__file__)`-relative any more now that this script lives in the engine
rather than beside them (`docs/plans/2026-09-18-doe-holds-no-scripts.md` § Path resolution).
Resolution order: `--root` override, then `CLAUDE_PLUGIN_ROOT`/the ambient plugin-root probe
(`coordinator_core.warm.caller_context.resolve_caller_context`, falling back to
`coordinator_core.subagent_sandbox.provision_report.resolve_plugin_root`).

Exit codes: 0 = phrase present at both sites. 1 = phrase missing at a named site (named on
stdout). 2 = usage/environment error, including a named site file that does not exist, or the
plugin root cannot be resolved and `--root` was not given — a missing site is a loud failure,
never a skip.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C2.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DURABLE_PHRASE = "the coordinator's accumulated internal doctrine and decision corpus"

_SITES = (
    Path("docs") / "wiki" / "reviewer-pipeline.md",
    Path("snippets") / "prior-art-check-consumption.md",
)


def _plugin_root() -> "Path | None":
    """The plugin content root the published doctrine-asset sites live under.

    Engine imports happen here, inside a function, never at module scope — keeps the module
    body pure so `serve_classifier` still classifies this file warm-servable.
    """
    try:
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.require_engine_on_path(__file__)
        from coordinator_core.warm.caller_context import resolve_caller_context

        ctx = resolve_caller_context()
        if ctx.plugin_root:
            return Path(ctx.plugin_root)
    except Exception:
        pass
    try:
        from coordinator_core.subagent_sandbox.provision_report import resolve_plugin_root

        root = resolve_plugin_root()
        return Path(root) if root else None
    except Exception:
        return None


def _repo_root() -> "Path | None":
    return _plugin_root()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check-prior-art-enumeration-drift",
        description="Flag a prior-art describer site missing the durable corpus phrase.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="doctrine-asset root to scan (default: resolved through the plugin root)",
    )
    args = parser.parse_args(argv)

    root = args.root or _repo_root()
    if root is None:
        print(
            "check-prior-art-enumeration-drift: cannot resolve the doctrine-asset root — "
            "the plugin root did not resolve and --root was not given",
            file=sys.stderr,
        )
        return 2

    missing: list[Path] = []
    for site in _SITES:
        path = root / site
        try:
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        except OSError as exc:
            print(
                f"check-prior-art-enumeration-drift: cannot read site {site}: {exc}",
                file=sys.stderr,
            )
            return 2
        if _DURABLE_PHRASE not in text:
            missing.append(site)

    if missing:
        print("check-prior-art-enumeration-drift: durable phrase missing at:")
        for site in missing:
            print(f"  {site}")
        return 1

    print("check-prior-art-enumeration-drift: PASS — durable phrase present at both sites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
