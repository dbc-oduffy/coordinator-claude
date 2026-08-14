# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""update-docs-probes.py — thin exit-code-contract shim over
`coordinator_core.ops.updatedocs_gates`'s 4 probe gates.

Port history: this file used to CARRY the fresh-scaffold-probe /
repomap-gate / queue-prune-sweep / distill-threshold logic directly (4
concerns, one subcommand each, ported from `coordinator/commands/update-
docs.md` bash fences). 2026-08-06 (cross-repo/inbox/2026-08-06-doe-claude-em-
updatedocs-gates-structured-verdicts.md, ADOPTED): that logic moved to
`coordinator_core/ops/updatedocs_gates.py`'s gate functions, which return a
structured `GateResult` (clean/finding/unavailable/contradiction + severity)
instead of a bare exit code — the native op is now the source of truth, and
this file's only remaining job is translating a `GateResult` back into the
legacy exit-code/stdout contract each `/update-docs` phase already expects,
so the phase prose in `coordinator/commands/update-docs.md` (DoE-claude, out
of this repo's edit scope) does not need to change in lockstep.

Each `_cmd_*` function below calls its gate function directly (in-process,
no subprocess/IPC round trip — the gate functions are already plain,
synchronous, side-effect-scoped callables) and re-derives the ORIGINAL
exit code from the returned `GateResult`. The mapping is per-subcommand
because the four original contracts were never uniform (see each
function's own docstring) — collapsing them into one generic translator
would silently change behavior a caller may depend on.

Retired 2026-07-29: the `snippet-sync-sweep` subcommand (Phase 11b glob-loop
over `bin/verify-*-sync.sh` verifiers) was removed as dead code — those
verifiers were retired fleet-wide (DoE-claude `dce9788bc` / `de23f5002`,
superseded by the native `coordinator_core/snippet_sync/` verifier), and no
caller passed a `--glob-root` pointing anywhere but the default `~/.claude`.
Its Windows-side `sh`/`bash` interpreter resolution (added 2026-07-28) was
Claude-klabauter's last unsanctioned bash dependency; removing the dead sweep removes
the dependency rather than sanctioning it. See CLAUDE.md § Runtime
conventions class (c) for the sibling retirement record.

Self-contained: every subcommand resolves its own repo-relative inputs from
an explicit `--repo-root` (default: cwd, matching the ceremony's own
cwd-at-repo-root invocation contract).

Sibling-CLI resolution asymmetry: `_cmd_repomap_gate` and `_cmd_queue_prune_sweep`
inject `_BIN_DIR` (this file's own `Path(__file__).parent`) as an override for
`check-rag-state.py` / `generate-repomap.py` / `prune-resolved-queue-entries.py`
before calling into `updatedocs_gates.py`'s gate functions, which otherwise
default to resolving CLIs under `settings_home / "bin"`. `_cmd_fresh_scaffold_probe`
and `_cmd_distill_threshold` pass no such override — they have no sibling CLI to
resolve. This file is now the ONLY place the `_BIN_DIR`-vs-`settings_home` split
lives; `updatedocs_gates.py` itself has no notion of "this file's own directory".
Review: coordinator:code-reviewer — flagged as under-documented relative to how
carefully every other design decision in this file is annotated.

Idempotent: every subcommand is read-mostly (queue-prune-sweep is the one
mutator, and it delegates the actual mutation + its own idempotency to
prune-resolved-queue-entries.py, unchanged) and may be re-run any number of
times with no side effects beyond what a clean re-run would have produced.

Usage:
  update-docs-probes.py fresh-scaffold-probe [--repo-root PATH]
  update-docs-probes.py repomap-gate [--repo-root PATH] [--rag-state STATE]
                                      [--check-rag-state-cli PATH]
                                      [--generate-repomap-cli PATH]
  update-docs-probes.py queue-prune-sweep [--repo-root PATH]
                                           [--prune-cli PATH]
                                           [--queue PATH ...]
  update-docs-probes.py distill-threshold [--repo-root PATH]
                                           [--log-path PATH]

Exit codes are documented per-subcommand in each `_cmd_*` function's
docstring below — they are NOT uniform across subcommands (this file is a
4-in-1 grab-bag of previously-independent bash fences, not one cohesive
tool with one exit-code contract).

Negative-spec: this file does NOT implement probe logic itself anymore —
adding a new axis/threshold/CLI-override belongs in
`coordinator_core/ops/updatedocs_gates.py`, not here. It does NOT run the
11f/11g/11h/11j gates that `updatedocs_gates.py` also carries — those never
had a CLI shim (DoE's Phase 11f/11g/11h/11j fences invoke the underlying
CLIs directly, see that module's docstring), so there is nothing here to
port them into.

Spec backlink: coordinator/commands/update-docs.md (DoE-claude) — Pre-flight
  probe, Phase 9b, Phase 11i, Phase 13 steps 1-2.
Spec backlink: cross-repo/inbox/2026-08-06-doe-claude-em-updatedocs-gates-
  structured-verdicts.md
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BIN_DIR = Path(__file__).resolve().parent
_REPO_ROOT_FOR_IMPORT = _BIN_DIR.parent.parent
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))

from coordinator_core.ops.updatedocs_gates import (  # noqa: E402
    GateVerdict,
    Severity,
    _gate_distill_threshold,
    _gate_fresh_scaffold_probe,
    _gate_queue_prune_sweep,
    _gate_repomap,
    _settings_home,
)


# ---------------------------------------------------------------------------
# fresh-scaffold-probe — Pre-flight: Fresh-Repo Precondition Probe
# ---------------------------------------------------------------------------


def _cmd_fresh_scaffold_probe(args: argparse.Namespace) -> int:
    """Delegates to `updatedocs_gates._gate_fresh_scaffold_probe`.

    Exit codes (unchanged legacy contract):
      0 — freshly-scaffolded (GateVerdict.FINDING); the no-op-loud message is
          printed to stdout. Caller should stop before dispatching the
          doc-maintenance agent.
      1 — not freshly-scaffolded (GateVerdict.CLEAN), OR the cwd guard fired
          (GateVerdict.UNAVAILABLE — neither CLAUDE.md nor .git/HEAD present,
          "not at repo root"). Caller should proceed with the normal
          pipeline; nothing is printed for either case.
    """
    result = _gate_fresh_scaffold_probe(Path(args.repo_root), Path(), {})
    if result.verdict == GateVerdict.FINDING:
        print(
            "Nothing material to update — the repo is freshly-scaffolded (no DIRECTORY.md, "
            "no completed work, no distillable artifacts in tasks/). /coordinator:repo-setup "
            "already produced the minimum-viable substrate (orientation_cache.md, "
            "project-tracker.md, README.md, CLAUDE.md). Re-run /update-docs after the first "
            "workstream lands real content.\n\n"
            "Doctrine: docs/wiki/produce-not-prescribe.md — setup-class skills produce "
            "minimum-viable downstream artifacts; downstream skills add-to them as content "
            "accumulates."
        )
        return 0
    return 1


# ---------------------------------------------------------------------------
# repomap-gate — Phase 9b: Repomap Regeneration (RAG-gated)
# ---------------------------------------------------------------------------


def _cmd_repomap_gate(args: argparse.Namespace) -> int:
    """Delegates to `updatedocs_gates._gate_repomap`.

    Exit codes (unchanged legacy contract):
      0 — gate resolved cleanly (fresh-skip, generation succeeded, or
          generation was skipped because the generator script is missing).
      1 — the generator was invoked and returned non-zero
          (GateVerdict.FINDING).
    """
    overrides = {
        "rag_state": args.rag_state,
        "check_rag_state_cli": args.check_rag_state_cli,
        "generate_repomap_cli": args.generate_repomap_cli,
    }
    settings_home = _settings_home(None)
    # repomap-gate resolves sibling CLIs from THIS bin/ dir, not
    # $COORDINATOR_SETTINGS_HOME/bin — override defaults directly when unset.
    if not overrides["check_rag_state_cli"]:
        overrides["check_rag_state_cli"] = str(_BIN_DIR / "check-rag-state.py")
    if not overrides["generate_repomap_cli"]:
        overrides["generate_repomap_cli"] = str(_BIN_DIR / "generate-repomap.py")

    result = _gate_repomap(Path(args.repo_root), settings_home, overrides)
    print(result.summary)
    if result.verdict == GateVerdict.FINDING:
        return 1
    return 0


# ---------------------------------------------------------------------------
# queue-prune-sweep — Phase 11i: Prune resolved-state bloat from queues
# ---------------------------------------------------------------------------


def _cmd_queue_prune_sweep(args: argparse.Namespace) -> int:
    """Delegates to `updatedocs_gates._gate_queue_prune_sweep`.

    Exit codes (unchanged legacy contract):
      0 — every existing legacy queue file's prune invocation exited 0, and
          every present YAML family's ceremony wrapper exited 0
          (GateVerdict.CLEAN or FINDING/INFORMATIONAL).
      1 — at least one legacy prune invocation exited non-zero, or a YAML
          family's ceremony wrapper CLI is missing
          (GateVerdict.FINDING/BLOCKING).
    """
    overrides = {
        "prune_cli": args.prune_cli or str(_BIN_DIR / "prune-resolved-queue-entries.py"),
        "queues": args.queue,
    }
    # `_gate_queue_prune_sweep` computes `bin_dir = settings_home / "bin"`
    # internally (its YAML-family leg has no per-CLI override, unlike the
    # legacy leg's `prune_cli`) -- pass `_BIN_DIR`'s PARENT here, not
    # `_BIN_DIR` itself, so that internal join resolves back to this file's
    # own `bin/` dir instead of double-nesting into `bin/bin/`.
    result = _gate_queue_prune_sweep(Path(args.repo_root), _BIN_DIR.parent, overrides)
    print(result.summary)
    for line in result.detail.get("lines", []):
        print(line, file=sys.stderr if result.severity == Severity.BLOCKING else sys.stdout)
    return 1 if result.severity == Severity.BLOCKING else 0


# ---------------------------------------------------------------------------
# distill-threshold — Phase 13: Artifact Distillation (Conditional), steps 1-2
# ---------------------------------------------------------------------------


def _cmd_distill_threshold(args: argparse.Namespace) -> int:
    """Delegates to `updatedocs_gates._gate_distill_threshold`.

    Exit codes (unchanged legacy contract):
      0 — threshold NOT met (GateVerdict.CLEAN; distillation not needed).
      1 — threshold met (GateVerdict.FINDING; caller should chain /distill).
    """
    overrides = {"log_path": args.log_path}
    result = _gate_distill_threshold(Path(args.repo_root), Path(), overrides)
    print(result.summary)
    return 1 if result.verdict == GateVerdict.FINDING else 0


def _cmd_snippet_sync_sweep_retired(_args: argparse.Namespace) -> int:
    """Accept the retired `snippet-sync-sweep` verb and do nothing. Exit 0.

    Exit 0 is the point: the sweep's contract was "0 when every verifier
    passed, and 0 when none matched the glob". None have matched anywhere in
    the fleet since the `verify-*-sync.sh` leg was retired, so a no-op returns
    exactly what a live sweep would have returned on this tree — the caller
    cannot tell the difference, which is what makes removing the body safe
    ahead of removing the call.

    Says so on stderr rather than silently: a Phase 11b that prints nothing at
    all reads as a probe that ran and found nothing, and the next person
    debugging a snippet-sync drift deserves to know this stopped checking.
    """
    print(
        "[update-docs] snippet-sync-sweep is retired (the verify-*-sync.sh leg it "
        "swept no longer exists fleet-wide; the native coordinator_core/snippet_sync/ "
        "verifier supersedes it) — accepting the verb as a no-op until the "
        "coordinator doctrine repo's Phase 11b invocation is dropped.",
        file=sys.stderr,
    )
    return 0


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="update-docs-probes.py",
        description="Thin exit-code shim over coordinator_core.ops.updatedocs_gates (4 subcommands).",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_fresh = sub.add_parser("fresh-scaffold-probe", help="Pre-flight fresh-repo precondition probe (3-axis AND).")
    p_fresh.add_argument("--repo-root", default=os.getcwd())
    p_fresh.set_defaults(func=_cmd_fresh_scaffold_probe)

    p_repomap = sub.add_parser("repomap-gate", help="Phase 9b RAG-state case dispatch -> conditional repomap regen.")
    p_repomap.add_argument("--repo-root", default=os.getcwd())
    p_repomap.add_argument("--rag-state", default=None, choices=["fresh", "absent", "stale", "unknown"])
    p_repomap.add_argument("--check-rag-state-cli", default=None)
    p_repomap.add_argument("--generate-repomap-cli", default=None)
    p_repomap.set_defaults(func=_cmd_repomap_gate)

    p_queue = sub.add_parser("queue-prune-sweep", help="Phase 11i 3-queue prune-and-report loop.")
    p_queue.add_argument("--repo-root", default=os.getcwd())
    p_queue.add_argument("--prune-cli", default=None)
    p_queue.add_argument("--queue", action="append", default=None, help="repeatable; overrides the default 3-queue list")
    p_queue.set_defaults(func=_cmd_queue_prune_sweep)

    p_distill = sub.add_parser("distill-threshold", help="Phase 13 artifact-count aggregation + fire/no-fire threshold.")
    p_distill.add_argument("--repo-root", default=os.getcwd())
    p_distill.add_argument("--log-path", default=None)
    p_distill.set_defaults(func=_cmd_distill_threshold)

    # Retirement shim, not a subcommand — see _cmd_snippet_sync_sweep_retired.
    p_retired = sub.add_parser("snippet-sync-sweep", help=argparse.SUPPRESS)
    p_retired.add_argument("--glob-root", default=None)
    p_retired.set_defaults(func=_cmd_snippet_sync_sweep_retired)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
