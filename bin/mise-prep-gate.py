"""mise-prep-gate.py — thin door-served CLI over `coordinator_core.roadmap.prep_gate_cli`.

The published surface (`skills/plan-blitz/mise-prep-entry.py :: _gate_cmd`) probes this
exact path — `<plugin_root>/bin/mise-prep-gate.py` — so the file name and location stay
fixed even though the bar it runs now lives entirely in the engine.

`main(argv)` shim, `coordinator/bin/plan-task-brief.py :: main` shape: engine imports
happen inside `main()`, the module body stays pure, so `serve_classifier` classifies
this file warm-servable. Every predicate (SPINE/CENSUS/EXTERNAL_DEPS/PRIME_EXIT/SCHEMA)
is `coordinator_core.roadmap.prep_gate.gate_plan`, called once per target — no spawn, no
git, no corpus-wide sweep. Argument parsing, target expansion and `--json`/`--tally`
rendering live in `coordinator_core.roadmap.prep_gate_cli`; this file owns nothing but
the door.

Coordinator-content-repo's own `coordinator/bin/mise-prep-gate.py` calls this file's module-level API
directly (`GateError`, `_resolve_engine_root`, `prep_gate`, `corpus_inputs`, `fleet_siblings`,
`_targets`, `main`, `_tally`, `_authoring_fix_lines`, `_is_settings_home_path`, the
`EXIT_*`/`PREPPED`/`NOT_PREPPED`/`ENGINE_ERROR`/`FLEET_REPOS`/`REQUIRES_VALUES` constants,
and `_attest`) — parity DoE's own tests hold this file to. Every name below is either a
direct re-export of the engine symbol it stands for, or a thin adapter over one: no
predicate is restated here, only shaped to the signature/argv convention DoE's callers
expect.

Usage:
  python mise-prep-gate.py [target ...] [--json] [--tally] [--repo-root PATH]

Exit codes (`coordinator_core.roadmap.prep_gate_cli`):
  0 — every named plan is PREPPED.
  1 — at least one plan is NOT-PREPPED (an authoring fix).
  2 — RESERVED (REFUSED — currently unreachable; see `prep_gate.py`'s own docstring).
  3 — usage error (bad target, coordinator_core unresolvable).
  4 — an engine defect on at least one target (PM/engineering, not an authoring fix);
      the rest of the batch still ran and reports its own verdict.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk S1-C8.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

class GateError(RuntimeError):
    """`coordinator_core` could not be resolved on `sys.path` from this file's
    location — the one precondition every module-level name below depends on.
    """


def _resolve_engine_root() -> Path:
    """The engine root (the tree containing `coordinator_core/`), or raise
    `GateError` naming the precondition that failed.

    Delegates the actual path-finding to `cc_invoke.require_engine_on_path` —
    the same bootstrap `main()` already uses — so this file has exactly one
    opinion about where the engine lives. Cheap and idempotent: callers (this
    module's own fixtures among them) may call it more than once per process.
    """
    try:
        # Plain-script execution puts this file's own directory on sys.path[0]
        # automatically; a caller that loads this module via
        # `importlib.util.spec_from_file_location` (every consumer of the
        # module-level API this file exists to expose, DoE's own tests
        # included) does not get that for free, so `import lib` below would
        # fail to find `coordinator/bin/lib/` from a foreign cwd. Added
        # unconditionally and idempotently — a second insert is a no-op cost,
        # never a correctness one.
        own_dir = str(Path(__file__).resolve().parent)
        if own_dir not in sys.path:
            sys.path.insert(0, own_dir)
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        root = cc_invoke.require_engine_on_path(__file__)
    except Exception as exc:  # noqa: BLE001 - re-raised as this module's own error type
        raise GateError(f"coordinator_core unresolvable: {exc}") from exc
    return Path(root) if root is not None else Path(__file__).resolve().parents[2]


def _engine():
    """`coordinator_core.roadmap.prep_gate`, imported only once the engine root
    is confirmed resolvable — never at module import time, so this file stays
    warm-servable (`serve_classifier`) even when `coordinator_core` is absent.
    """
    _resolve_engine_root()
    from coordinator_core.roadmap import prep_gate

    return prep_gate


def _cli():
    _resolve_engine_root()
    from coordinator_core.roadmap import prep_gate_cli

    return prep_gate_cli


# ---------------------------------------------------------------------------
# Vocabulary — re-exported by name, not restated, and resolved on first read
# (PEP 562) so the module body stays inert for `serve_classifier`. A read made
# before the engine is resolvable raises `AttributeError`, as an absent name
# would, rather than a half-populated module.
# ---------------------------------------------------------------------------

_PREP_GATE_NAMES = frozenset(
    {
        "PREPPED",
        "NOT_PREPPED",
        "REFUSED",
        "ENGINE_ERROR",
        "FLEET_REPOS",
        "REQUIRES_VALUES",
        "STAMP_FIELDS",
        "fleet_siblings",
        "repo_root_names",
        "repo_nested_names",
        "_is_settings_home_path",
        "_authoring_fix_lines",
        "_terminal_statuses",
    }
)
_PREP_GATE_CLI_NAMES = frozenset(
    {
        "EXIT_PREPPED",
        "EXIT_NOT_PREPPED",
        "EXIT_REFUSED",
        "EXIT_USAGE",
        "EXIT_ENGINE_ERROR",
        "GateCLIError",
    }
)


def __getattr__(name: str):
    if name in _PREP_GATE_NAMES:
        source = _engine
    elif name in _PREP_GATE_CLI_NAMES:
        source = _cli
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        return getattr(source(), name)
    except GateError as exc:
        raise AttributeError(f"{name}: {exc}") from exc


def corpus_inputs(repo_root: Path) -> Any:
    """The two per-corpus facts every predicate reads (`root_names`, `siblings`,
    `nested_names`), resolved once and reused across every plan a caller gates
    standing in the same `repo_root` — `coordinator_core.roadmap.prep_gate.corpus_inputs`
    verbatim.
    """
    return _engine().corpus_inputs(Path(repo_root))


def prep_gate(plan_path: Path, corpus: Any) -> Dict[str, Any]:
    """The whole bar over ONE plan, given an already-resolved `corpus_inputs()`.

    `coordinator_core.roadmap.prep_gate.gate_plan_with_corpus` verbatim — this
    file adds no predicate, only the plan-first calling shape DoE's own callers
    use (`gate_plan` itself is repo-root-first, for the write op's per-call
    convention; both reach the same `evaluate_plan`).
    """
    return _engine().gate_plan_with_corpus(Path(plan_path), corpus)


def _targets(args: List[str], repo_root: Path) -> List[Path]:
    """Plan file(s) named by `args`, directories expanded and sidecars pruned —
    `coordinator_core.roadmap.prep_gate_cli._targets` verbatim.
    """
    try:
        return _cli()._targets(args, Path(repo_root))
    except _cli().GateCLIError as exc:
        raise __getattr__("GateCLIError")(str(exc)) from exc


def _tally(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The corpus tally over `reports` — verdict counts, defect-kind counts, and
    `not_prepped_terminal` (a NOT-PREPPED plan whose `status:` already ran; see
    `_terminal_statuses`) — `coordinator_core.roadmap.prep_gate_cli._tally` verbatim.
    """
    return _cli()._tally(reports)


def main(argv: "list[str] | None" = None) -> int:
    """`argv` carries the program name at `[0]`, DoE's own convention for this
    entrypoint (`sys.exit(main(sys.argv))` at the bottom of this file) — stripped
    here before handing the rest to `prep_gate_cli.main`, which expects an argv
    with the program name already removed (`argparse`'s own convention). A
    caller supplying `None` gets the live `sys.argv`, program name included, so
    both callers agree on what "argv" means without this file parsing twice.
    """
    raw = argv if argv is not None else sys.argv
    try:
        cli = _cli()
    except GateError as exc:
        print(f"mise-prep-gate.py: ERROR — coordinator_core unresolvable: {exc}", file=sys.stderr)
        return 3
    return cli.main(list(raw[1:]))


#: The mise-prep attest field names, in report order — presentation-only
#: vocabulary local to this file's `_attest`, restated from `STAMP_FIELDS`
#: rather than a second literal tuple, so the two cannot drift apart.
def _attest(text: str, fm: Dict[str, Any]) -> "Optional[str]":
    """Report the mise-prep attest (`mise_prepped_by/_at/_sha/_findings`) as one
    line, or `None` when there is nothing worth saying about it. This bar
    REPORTS the attest and never gates on it — widening it to refuse a plan
    over a field this module does not stamp would deadlock the stamp's own
    repair path.

    Reported by example-store-repo-fb, both halves observed rather than reasoned: a
    plan carrying no `mise_prepped_*` field at all reported PREPPED — nobody
    prepped it, it was merely well-authored — and a plan whose stamped
    `mise_prepped_sha` no longer covered a body a reviewer integration had
    since rewritten reported PREPPED with no word about the sha. An attest
    whose staleness nothing checks is the decay the sha exists to prevent.

    UNSTAMPED / MALFORMED / STALE / (silently CERTIFIED, no line at all) are
    four different facts and stay four different lines: a reader told
    "not certified" re-stamps, a reader told "the body changed" re-gates, and
    collapsing UNSTAMPED into MALFORMED sends an author to re-stamp a plan
    whose defects were never re-checked.

    THE SHA COMES FROM THE ENGINE, NEVER A SECOND TRANSCRIPTION — recomputed
    here via `canonical_body_sha`, the exact recipe the write side stamps
    with, so a recipe drift cannot silently report every certified plan
    stale. `mise_prepped_findings` participates in the presence/MALFORMED
    check exactly like every other stamp field — it is NOT CHECKED for
    content here, only for presence, because re-deriving the findings a stamp
    recorded is the write side's job, not this read-only report's.

    COUPLED TO THE PREPPED verdict computed by whichever caller decides
    whether to print this line at all (see `main()`'s `show = attest and ...`
    guard below) — that is the intent, not an oversight: several hundred
    plans predate this bar, and a line printed on every one of them says
    nothing their own defect list does not. A STALE attest still matters
    under NOT-PREPPED, where it still misleads a reader who trusts the stamp
    over the bar's own live verdict; an absent one does not, because
    NOT-PREPPED already says the plan is unstamped in every sense that
    matters.

    Negative-spec:
      - Does NOT change the verdict this bar returns. `plan.stamp_prepped`
        refuses on a non-PREPPED verdict and writes the stamp; this function
        reads what that write left behind, after the fact, and never before.
        COUPLED TO THE PREPPED verdict only for WHETHER it is shown, never
        for what it computes — that is the intent stated above.
      - Does NOT re-derive `mise_prepped_findings`. Presence only.
      - Zero subprocess, zero git: the sha comes from `canonical_body_sha`,
        a pure read over `text` already in memory, the same recipe the write
        side (`coordinator_core.roadmap.prep_gate.read_stamp`) uses.
    """
    from coordinator_core.frontmatter.primitives import canonical_body_sha

    stamp_fields = _engine().STAMP_FIELDS
    present = [field for field in stamp_fields if field in fm]
    if not present:
        return (
            "  attest:        no prep attest recorded -- this is not a record that "
            "anyone prepped it, only that the bar above currently passes"
        )
    missing = [field for field in stamp_fields if field not in fm]
    if missing:
        return f"  attest:        MALFORMED -- missing {', '.join(missing)}"
    recorded_sha = str(fm.get("mise_prepped_sha") or "").strip()
    body_sha = canonical_body_sha(text) or ""  # NOT CHECKED against findings content, sha only
    if recorded_sha and body_sha and recorded_sha.lower() == body_sha.lower():
        return None
    return "  attest:        STALE -- mise_prepped_sha no longer covers this body"


def _yaml_error_detail(exc: Exception) -> str:
    """One-line rendering of a YAML parse failure, for a caller reporting a
    frontmatter defect outside the engine's own `frontmatter_parse_error`
    (which already renders this for the bar's SCHEMA class). Kept here for a
    caller of this file that wants the same wording without importing the
    engine's frontmatter module directly.
    """
    mark = getattr(exc, "problem_mark", None)
    if mark is not None:
        location = f"line {mark.line + 1}, column {mark.column + 1}"
    else:
        location = "unknown location"
    problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
    return f"YAML parse error at {location}: {problem}"


if __name__ == "__main__":
    sys.exit(main(sys.argv))
