# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
reap-orphaned-in-flight-handoffs.py — thin CLI shell over
coordinator_core.ops.reap_in_flight_claims's survey()/apply_dispositions().

Purpose, per `docs/plans/2026-08-26-two-callers-want-two-numbers-not-a-1301-line-cli.md`
chunk C3: the fused read-side implementation this file used to carry measured
515.6ms warm, which DR-344 § 6 dispositions as Deleted — "the deleted code is
not a starting point, not a reference, and not a thing to be 'earned back'."
C1 (`coordinator_core.ops.reap_in_flight_claims`) rebuilt the job — "release
crash-orphaned claims on consumed+in_flight handoffs, name the ones it cannot
dispose of" — from the requirement, in one corpus pass. This file is what
remains at the NAME: argument parsing, a call into that op, and printing.

The NAME stays: `coordinator_core.workday_complete.brief`'s
`CONSUMES_MANIFEST` is a closed set carrying `"reap-orphaned-in-flight-
handoffs"` as a live directive — renaming or relocating this entrypoint
breaks that caller even though the implementation behind it changed
completely.

Usage:
    reap-orphaned-in-flight-handoffs.py [--dry-run] [--repo-root PATH]

  --dry-run     Survey and print dispositions; mutate nothing.
  --repo-root   Explicit repo root (bypasses the checked resolver's cwd walk;
                mirrors sibling `coordinator/bin` CLIs' own --repo-root flag).
  -h, --help    Show this help and exit.

Default (no flags) surveys AND applies every mutating disposition — this is
the shape `workday_complete/brief.py`'s `args=[]` directive depends on; a
--dry-run-by-default CLI would silently stop releasing/reclaiming claims for
that caller.

Exit codes:
  0  survey (and, unless --dry-run, apply) completed with no failed writes
  1  repo root unresolvable, or one or more dispositions failed to apply
  2  invalid flags

Negative-spec:
    - Does NOT re-implement any part of the survey — every predicate
      (census, live-holder check, live-children check, governed-plan
      pre-check, ship-detection) lives in `reap_in_flight_claims.py`; this
      file never reads `state/handoffs` itself.
    - Does NOT parse or emit prose a caller must regex — the two integers
      (`would_release`, `would_reclaim`) and each disposition's structured
      fields are read straight off `SurveyResult`/`Disposition`, never
      reconstructed from a printed sentence.
    - Does NOT fall back to any prior fused behavior on an op-call failure —
      no escape hatch; a `survey()`/`apply_dispositions()` exception
      propagates.

Spec backlink: docs/plans/2026-08-26-two-callers-want-two-numbers-n-6127ee.md § C3
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

SELF_NAME = "reap-orphaned-in-flight-handoffs"

_BOOTSTRAP_NAMES = ("resolve_checked_repo_root", "survey", "apply_dispositions")


def __getattr__(name: str):
    """PEP 562 module `__getattr__` -- lets a caller that reaches for one of
    the bootstrap-deferred names (e.g. this file's own test suite, which
    monkeypatches `mod.resolve_checked_repo_root`/`mod.survey`/
    `mod.apply_dispositions` ahead of calling `mod.main()`; `pytest`'s
    `monkeypatch.setattr` itself calls `getattr()` first to save the prior
    value, which is what actually triggers this) run `_bootstrap_imports()`
    lazily on first access, instead of requiring the name to already be a
    module global at import time. Only fires when the name is NOT already
    present in this module's `__dict__` -- once `_bootstrap_imports()` has
    run once (via this hook or via `main()`), the plain global wins on every
    later lookup and this function is not called again for that name."""
    if name in _BOOTSTRAP_NAMES:
        _bootstrap_imports()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _bootstrap_imports() -> None:
    """Import every non-stdlib dependency this module needs and bind it at
    module scope, called from main() (C6k import-motion: module bodies stay
    inert on both the warm door and the un-bootstrapped settings-home
    forwarder load routes). Order is load-bearing — preserved verbatim from
    the former module-scope sequence. Idempotent by construction: a name
    already bound at module scope (via a prior call, or a test's own
    `monkeypatch.setattr(mod, "resolve_checked_repo_root", ...)` ahead of
    calling `main()`) is left alone rather than clobbered by a real import.
    """
    if "resolve_checked_repo_root" in globals():
        return

    global resolve_checked_repo_root, survey, apply_dispositions

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import ensure_engine_on_path
    from repo_identity import resolve_checked_repo_root

    ensure_engine_on_path(__file__)

    from coordinator_core.ops.reap_in_flight_claims import (
        apply_dispositions,
        survey,
    )

HELP_TEXT = """\
reap-orphaned-in-flight-handoffs — release crash-orphaned in_flight handoff
claims, and name the ones it cannot dispose of.

Usage:
  reap-orphaned-in-flight-handoffs [--dry-run] [--repo-root PATH]

Options:
  --dry-run       Survey and print dispositions; mutate nothing.
  --repo-root P   Explicit repo root (default: resolved from cwd).
  -h, --help      Show this help and exit.

Exit codes:
  0  success (no failed writes)
  1  repo root unresolvable, or a disposition failed to apply
  2  invalid flags
"""


def _usage_error(message: str) -> int:
    sys.stderr.write(f"{SELF_NAME}: {message}\n")
    return 2


def _parse_args(argv: List[str]) -> "tuple[Optional[dict], Optional[int]]":
    """Returns (config, None) on success, or (None, exit_code) on a
    terminal parse outcome (usage error or --help)."""
    cfg = {"dry_run": False, "repo_root": None}
    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        if arg == "--dry-run":
            cfg["dry_run"] = True
            i += 1
        elif arg == "--repo-root":
            if i + 1 >= n or not argv[i + 1]:
                return None, _usage_error("--repo-root requires a value")
            cfg["repo_root"] = argv[i + 1]
            i += 2
        elif arg in ("-h", "--help"):
            sys.stdout.write(HELP_TEXT)
            return None, 0
        else:
            return None, _usage_error(f"unknown flag {arg!r}\n  Use --help for usage.")
    return cfg, None


def _resolve_repo_root(explicit_root: Optional[str]) -> Optional[str]:
    """The checked resolver (repo_identity) — a MISMATCH is advisory only
    (warn to stderr, proceed with the resolved root); UNRESOLVED never
    refuses. An explicit --repo-root bypasses the resolver/gate entirely
    (EXPLICIT verdict), same as every other migrated `coordinator/bin` CLI."""
    _bootstrap_imports()
    root, verdict = resolve_checked_repo_root(explicit_root=explicit_root)
    if verdict.get("verdict") == "MISMATCH":
        sys.stderr.write(f"{SELF_NAME}: {verdict.get('message')}\n")
    return root


def _print_report(result, *, dry_run: bool) -> None:
    for d in result.dispositions:
        sha_suffix = f" sha={d.sha}" if d.sha else ""
        print(f"[{d.verdict}] {d.path} (holder={d.holder}){sha_suffix}: {d.detail}")
    print(f"would_release={result.would_release} would_reclaim={result.would_reclaim}")
    if dry_run:
        print("[dry-run] no changes made")


def main(argv: Optional[List[str]] = None) -> int:
    _bootstrap_imports()
    args = list(sys.argv[1:] if argv is None else argv)

    cfg, terminal_rc = _parse_args(args)
    if terminal_rc is not None:
        return terminal_rc

    repo_root = _resolve_repo_root(cfg["repo_root"])
    if not repo_root:
        sys.stderr.write(
            f"{SELF_NAME}: cannot resolve git repo root from {os.getcwd()}\n"
        )
        return 1

    result = survey(Path(repo_root))
    _print_report(result, dry_run=cfg["dry_run"])

    if cfg["dry_run"]:
        return 0

    _applied, failed = apply_dispositions(result.dispositions)
    if failed:
        for detail in failed:
            sys.stderr.write(f"{SELF_NAME}: {detail}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
