# Filename drops the `.sh` suffix (matches coordinator-auto-push / handoff-gate-aging /
# backfill-initiative-fk) — there is no live caller of the literal
# "backfill-deliverable-spine.sh" name (confirmed: one-shot migration tool, already ran
# to completion 2026-07-06 per state/handoffs/2026-07-06_185802_*.md; the corpus scan is
# idempotent/re-runnable but nothing else invokes it), so dropping the suffix needs no
# caller repoint.
#
# backfill-deliverable-spine — CLI trampoline over claude-klabauter
# coordinator_core.ops.backfill_deliverable_spine.
#
# Backfill deliverable_id onto the fleet artifact corpus (handoff / plan / spinoff /
# roadmap / completion). Groups by workstream/chain key, emits a human-reviewable
# GROUPING REPORT, and (with --write) stamps deliverable_id onto mutable artifacts.
# Archived/immutable artifacts are reported but never written; already-threaded
# artifacts are never re-minted.
#
# Shebang note: the SHEBANG line above is `#!/usr/bin/env python3`, and correct
# for this shape. On Windows, this file's co-located `.cmd` twin wins via
# `PATHEXT` when invoked as a bareword, so the shebang is never read there; on
# macOS/Linux `python3` is the right interpreter. Caution: callers must invoke
# via the extensionless name or a resolved-interpreter prefix, never a bareword
# `.py` through git-bash — git-bash DOES honor the shebang and would exec-127
# with no `python3` present. See the carve-out in DoE-claude's
# coordinator/docs/wiki/bash-on-windows-gotchas.md § Carve-out (cross-repo —
# this wiki lives in the DoE-claude repo, not here).
#
# Usage:
#   backfill-deliverable-spine [--dry-run] [--root <coordinator-root>]
#   backfill-deliverable-spine --write [--root <coordinator-root>]
#
# Exit codes:
#   0 — clean (no ambiguities; write applied or dry-run report emitted)
#   1 — fatal error (bad arguments, corpus root unreadable)
#   2 — ambiguous groups detected (human review required before --write)
#   3 — TRANSPORT FAILURE — CLAUDE_KLABAUTER_ROOT resolution failed or
#       coordinator_core.ops.backfill_deliverable_spine not importable. Dedicated
#       code per the porter addendum §3b (fail-loud gate/validator scripts): this
#       tool's own business codes already occupy 0/1/2, so a transport outage
#       cannot reuse any of them without a caller misclassifying a claude-klabauter-link
#       failure as "clean" / "usage error" / "ambiguous groups". On CLAUDE_KLABAUTER_ROOT
#       resolution failure specifically, this is a KNOWN systemic cold-machine
#       issue (a fresh install may not yet have CLAUDE_KLABAUTER_ROOT resolvable) — the
#       error message below names the remediation.
#
# Spec backlink: pln-fleet-deliverable-spine-identity-and-facets-2b331c § C5, AC7
# Port backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md § BIG_PORT Wave C

from __future__ import annotations

import os
import sys
from typing import Optional

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402
from coordinator_registry import _DoeUnresolvable, doe_root  # noqa: E402

_TRANSPORT_FAILURE_EXIT = 3

# The corpus classes `coordinator_core.ops.backfill_deliverable_spine.enumerate_corpus`
# walks. A resolved default root containing none of these is the exact
# silent-empty-scan failure mode this memo-driven fix exists to catch —
# see `_validate_default_root_has_corpus`.
_CORPUS_CLASS_RELPATHS = ("state/handoffs", "docs/plans", "archive/completed")


def _resolve_default_coordinator_root() -> Optional[str]:
    """Resolve the default corpus root (DoE-claude's repo root).

    This is the root the ported op walks for ``state/handoffs``,
    ``docs/plans``, ``archive/completed``, etc. (see
    ``coordinator_core.ops.backfill_deliverable_spine.enumerate_corpus``).

    The corpus root is DoE-claude's own repo root, NOT its ``coordinator/``
    plugin subtree. Per cross-repo memo
    ``2026-08-08-doe-claude-em-backfill-spine-default-root-misses-the-corpus.md``,
    the ``<doe_root()>/coordinator`` reading (empirically inferred from the
    tool's one prior real run, commit ``aa98455f`` in DoE-claude,
    2026-07-06, which happened to stamp two files under
    ``coordinator/docs/plans/``) was already wrong for ``state/handoffs``
    (never under ``coordinator/``) and was made wrong for ``docs/plans``
    too once DoE-claude's migration moved that corpus class to
    ``<doe_root()>/docs/plans/``. Verified against DoE-claude's live disk:
    ``state/handoffs`` and ``docs/plans`` exist directly under
    ``doe_root()``, not under ``doe_root()/coordinator``; only
    ``archive/completed`` happens to exist under both, which is what let
    the old reading keep looking plausible. Do not re-append
    ``"coordinator"`` here — that reintroduces this defect. (Other tools in
    this repo, e.g. ``verify-templates-bin-sync.py``, legitimately resolve
    ``<doe_root()>/coordinator`` for the coordinator-claude *plugin*
    subtree — templates, skills, cockpit-contract schema — which is a
    distinct concept from this op's fleet-artifact *corpus*. Do not conflate
    the two.)

    Env var ``CLAUDE_PLUGIN_ROOT`` wins if set, returned verbatim.
    Otherwise resolves via ``doe_root()`` and returns it directly.

    This does NOT derive from this script's own ``__file__`` location.
    That was correct when this executable lived in DoE-claude
    (``coordinator/bin/.. IS`` the plugin root there), but this file has
    since migrated to claude-klabauter while DoE-claude's corpus
    (``state/``, ``docs/``, ``archive/``) stayed put in DoE-claude —
    self-location now resolves to ``<claude-klabauter>/coordinator``, a directory
    with none of those subdirs at all, so the corpus scan silently returns
    empty instead of failing loud. A future reader must not "restore"
    ``__file__``-based resolution to regain oracle parity — that is
    precisely what caused this break.

    Returns ``None`` (rather than exiting) when ``doe_root()`` is
    unresolvable — the caller may still supply ``--root`` explicitly on
    the command line, which the op honors ahead of this default; only if
    neither is available does the op's own fallback fail loud (see
    ``coordinator_core.ops.backfill_deliverable_spine.main``'s no-root
    branch).
    """
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return env_root
    try:
        return doe_root()
    except _DoeUnresolvable:
        return None


def _validate_default_root_has_corpus(default_root: str) -> Optional[str]:
    """Sanity-check a resolved DEFAULT root before handing it to the op.

    Only called for the default (env/``doe_root()``-derived) root, never for
    an explicit ``--root`` — an operator passing ``--root`` has taken
    responsibility for that path themselves.

    Threshold: requires ALL of ``_CORPUS_CLASS_RELPATHS``, not "any one".
    ``archive/completed`` exists under BOTH ``doe_root()`` and
    ``doe_root()/coordinator`` (see the ``_resolve_default_coordinator_root``
    docstring) — it is the exact confounder that let the old buggy
    ``<doe_root()>/coordinator`` reading "keep looking plausible". Review:
    coordinator:code-reviewer — an "any of three" threshold shares the
    historical bug's own blind spot: a future regression that re-appends
    ``"coordinator"`` to the default root would resolve a root where only
    ``archive/completed`` is present, and "any" would pass it silently,
    leaving ``state/handoffs``/``docs/plans`` unscanned. Failing loud (not
    merely warning) on a partial match is deliberate: a partial-corpus
    default root is a silent-wrong-answer condition, and this whole fix
    exists because silent under-enumeration read as success. The explicit
    ``--root`` escape hatch already exists for an operator who genuinely
    wants to point at a partial root.

    Returns an error message string naming exactly which corpus classes are
    missing if fewer than all of ``_CORPUS_CLASS_RELPATHS`` exist under
    ``default_root`` (covers both the zero-present and partial-present
    cases), or ``None`` only when all three are present.
    """
    present = [
        relpath
        for relpath in _CORPUS_CLASS_RELPATHS
        if os.path.isdir(os.path.join(default_root, relpath))
    ]
    missing = [
        relpath for relpath in _CORPUS_CLASS_RELPATHS if relpath not in present
    ]
    if not missing:
        return None
    return (
        f"backfill-deliverable-spine: resolved default root {default_root!r} "
        f"is missing expected corpus class(es) ({', '.join(missing)}) — "
        f"present: ({', '.join(present) if present else 'none'}). A partial "
        "corpus root silently under-enumerates. Pass --root explicitly, or "
        "fix _resolve_default_coordinator_root()."
    )


def _import_runner():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the DR-276 runner.

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    DR-276: the op is run through `coordinator_core.cli_entry.run_op_main`
    rather than by calling its `main` directly, so the paths it declares become
    a session scope-touch claim. Without that, everything this CLI writes is an
    orphan at the `scoped_git_commit` sink.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.cli_entry import run_op_main

    return run_op_main


def main() -> None:
    try:
        run_op_main = _import_runner()
    except RuntimeError as exc:
        print(
            f"backfill-deliverable-spine: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}",
            file=sys.stderr,
        )
        print(
            "  This can happen on a fresh/cold install where CLAUDE_KLABAUTER_ROOT is not yet "
            "resolvable. Run `coordinator-claude-klabauter-root.sh` directly to diagnose, or set "
            "CLAUDE_KLABAUTER_ROOT explicitly.",
            file=sys.stderr,
        )
        sys.exit(_TRANSPORT_FAILURE_EXIT)
    except ImportError as exc:
        print(
            f"backfill-deliverable-spine: coordinator_core.cli_entry not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(_TRANSPORT_FAILURE_EXIT)

    # `run_op_main` only forwards argv to the op's `main(argv)` — it has no
    # channel for the op's `default_coordinator_root=` kwarg. Reproduce that
    # kwarg's effect by injecting `--root <default>` into argv ourselves,
    # UNLESS the caller already passed `--root` explicitly (which must win).
    argv = list(sys.argv[1:])
    # A help request must never depend on a resolvable corpus root — the
    # caller has not chosen a root yet, and the published-mirror entrypoint
    # gate runs `--help` against a hermetic fixture HOME that has no corpus
    # by construction.
    wants_help = any(arg in ("-h", "--help") for arg in argv)
    if "--root" not in argv and not wants_help:
        default_root = _resolve_default_coordinator_root()
        if default_root:
            validation_error = _validate_default_root_has_corpus(default_root)
            if validation_error:
                print(validation_error, file=sys.stderr)
                sys.exit(1)
            argv = argv + ["--root", default_root]

    try:
        code = run_op_main("coordinator_core.ops.backfill_deliverable_spine", argv)
    except ImportError as exc:
        print(
            "backfill-deliverable-spine: "
            f"coordinator_core.ops.backfill_deliverable_spine not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(_TRANSPORT_FAILURE_EXIT)

    sys.exit(code)


if __name__ == "__main__":
    main()
