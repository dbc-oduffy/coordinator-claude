"""
coordinator.bin.waste-signal -- dynamic, opt-in instrument counting call redundancy and the
work-vs-question ratio for one live-executed callable.

Arrival record: state/audits/doe-script-arrivals/W3-C3.yaml
(docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C3). Mechanical move from DoE-claude
coordinator/bin/waste-signal.py (1405 lines). `DR-180`'s "hosted in coordinator/bin/, not
Claude-klabauter's" line is the plane call this whole plan's PM ruling supersedes (DoE holds no
scripts) -- the instrument itself is unchanged; only its host tree moves. The only DoE-relative
seam this module carried was `_import_test_target_mapper`'s reach into `coordinator_core` across
a repo boundary via the DoE-side `_engine_root` shim (`coordinator/hooks/scripts/_engine_root.py`);
that boundary is gone now that this module's own tree IS the engine root (see
`_ensure_engine_on_path` below, § Path resolution).

Purpose: `docs/research/spike-verdicts/2026-08-27-call-redundancy-and-work-vs-question-detectability.md`
returned `viable` for the DYNAMIC form only (never a static linter -- Rice's theorem, and no
shipped tool in any registry implements this shape). This is a doctrine-plane reviewer's
instrument. This module is the rebuild-for-keeps of the spike's throwaway ninety-line probes.

NOT A SECURITY CONTROL. A Python-level `sys.addaudithook` is trivially bypassable by design --
only the C API `PySys_AddAuditHook()`, armed before interpreter init, is robust. This instrument
counts file-open-shaped events inside this repo's own process during a review; it makes no claim
about adversarial code and must never be cited as one.

MEASURED BYPASS ROUTES (Windows, this spike): `ctypes` straight into `CreateFileW` fires no audit
event named `open` at all -- a true blind spot, though `ctypes.dlsym` still fires and is recorded
as a bypass tell. `sqlite3` does real file I/O but fires `sqlite3.connect` / `sqlite3.connect/handle`,
never `open`. Both are why this module watches ALL audit events via a single `sys.addaudithook`
call rather than filtering to `open` -- filtering would silently drop the sqlite3 recovery and the
ctypes tell alike. Every event this module does not recognise is reported under `unknown_events`,
never dropped: a blind spot you can detect beats one you cannot (spike, "The Windows-coverage gap").

NEVER LOG FROM INSIDE THE HOOK. `logging` itself fires audit events, so a hook that logs recurses
(CPython bpo-98105 / gh-98105). The hook below does one thing -- increment counters in a plain
dict -- and nothing else. Reporting happens only after `disarm()`, outside the hook's call frame.

THRESHOLD DESIGN, STATED AS A DESIGN ACT (per the spike: "a ratio is not a threshold" -- 603:0 is
self-evidently bad, but nothing else establishes where a legitimately expensive set ends and a
wasteful one begins). Two thresholds, both absolute counts rather than ratios, both revisable:

- `REDUNDANT_OPEN_THRESHOLD = 10`: more than 10 exact-path repeats within one live call is flagged.
  Derived from the spike's own bracket -- the known-bad oracle (`_build_known_scope`) measured 163
  redundant opens per call; the known-fine cases in this repo's self-audit
  (`expired-plan-gates.py:71`, `statusline.py:226`) measure ZERO, because a proportional walk over
  a corpus touches each path once by construction. A double-digit threshold sits an order of
  magnitude below the known-bad case and two orders above the known-fine floor, so it tolerates a
  handful of legitimate re-opens (retries, re-reads across a multi-pass algorithm) without
  admitting the 603-open shape. NOT derived from a statistical model -- there is no corpus to fit
  one to (see plan `docs/plans/2026-08-27-waste-signal-instrument-and-its-real-boundary.md` C6:
  n=5 retrospective corpus is infeasible). Revisit if C6's discrimination check or C8's fleet
  self-audit finds it too loose or too tight.
- `ZERO_QUESTION_THRESHOLD`: not a number at all, by design -- any build cost (`open_count > 0`)
  paired with `query_count == 0` is flagged outright, regardless of scale. This sidesteps the
  ratio-at-zero-denominator failure mode entirely and is exactly the shape the spike measured as
  the common case (four of five scoped paths, zero questions asked of the built set).
- `OPENS_PER_QUESTION_THRESHOLD = 100`: when `query_count > 0`, flag if
  `open_count / query_count` exceeds 100. Derived from the spike's "staged deletion" case (603
  opens for 1 question = 603 opens/question, clearly wasteful) against a comfortable margin below
  it, so a proportional multi-question consumer is not caught by the same line that catches the
  oracle's single-question case.

AC8 (this dynamic half): neither signal here is cyclomatic complexity, the Maintainability Index,
Halstead, or a per-function length threshold -- the four the literature disqualifies
(`docs/research/2026-08-27-code-quality-signal-selection.md`). Call redundancy and the
work-vs-question ratio are novel dynamic instruments with no such literature verdict against them
either way; the spike is this repo's own evidence, not a borrowed one.

Zero-spawn does not apply -- this is a bin tool run deliberately on demand, never on the hook
hot path (`coordinator/hooks/scripts/_engine_root.py`'s zero-spawn constraint is scoped to
hot-path PreToolUse/PostToolUse dispatch).

ATTRIBUTION, MEASUREMENT STATUS, AND `--attribute-diff` (C1 of
docs/plans/2026-08-28-waste-number-reaches-the-reviewer.md). The spike verdict
(`docs/research/spike-verdicts/2026-08-27-waste-number-attributability-to-a-change.md`) measured
that an UNFILTERED redundant-open count is not merely noisy but actively misleading -- 370 of 374
redundant paths in a clean run are outside the repo entirely (stdlib, site-packages, `.pyc`,
editable-install path hooks), and an injected 136-open defect measured a NEGATIVE delta unfiltered
while measuring +133 filtered to in-repo paths. `CallRedundancyReport` now retains `path_counts`
(the join key `measure_call_redundancy` previously discarded at the report boundary) and
`attribute_redundant_opens()` filters it against a caller-supplied changed-path set, reporting
attributable / elsewhere-in-repo / out-of-repo (the last as one count, never enumerated) plus an
explicit `measured`/`not-measurable` status with a reason -- never inferred from a zero.
`evaluate_waste()` now takes the redundant-open count to judge as an explicit argument rather than
reading `report.redundant_opens` by default, so a caller cannot silently threshold the wrong basis
(10 and 13 are both correct numbers measured on different bases; see the spike). The
`--attribute-diff <repo-relative-path>...` CLI mode resolves covering tests for the given paths by
naming convention (the private engine binding `coordinator_core.ops.dispatch_emit.pathspec.
_map_written_path_to_test_target` -- import failure is fail-loud, never a reimplemented parallel
resolver), arms the hook, runs the resolved tests in one child process via `pytest.main()`, and
prints the attributed report as JSON on stdout. Only a crash BEFORE the hook could arm (engine/
import resolution) exits non-zero; a crash in the covering-test run itself degrades to a
`not-measurable` report on stdout with exit 0, converging with the no-executable-surface case.

Spec backlink: docs/plans/2026-08-27-waste-signal-instrument-and-its-real-boundary.md chunk C4;
docs/plans/2026-08-28-waste-number-reaches-the-reviewer.md chunk C1.

THE STATIC SIGNAL: project_duplicate_blocks AS A CANDIDATE GENERATOR (C1 of
docs/plans/2026-08-29-static-signal-is-a-candidate-generator.md). project-rag's
`project_duplicate_blocks` measured 100% precision on byte-identity
(`state/audits/2026-08-27-static-waste-signal-disposition.md`) and is the one static signal that
survived measurement, but its answer is a fact about an INDEX, never about the repo -- a derived,
re-projectable, staleness-prone snapshot per `CLAUDE.md`'s tri-plane table. This module therefore
treats it strictly as a CANDIDATE GENERATOR: nothing it returns reaches a reviewer un-reverified
against the working tree (that re-verification is C2's job; C1 is the call and the failure
taxonomy alone).

`fetch_duplicate_block_candidates()` speaks JSON-RPC over streamable HTTP to the direct daemon
port `127.0.0.1:8767/mcp` (`initialize` -> `notifications/initialized` -> `tools/call`), a
transport shape proven by execution this session and mirrored from project-rag's own
`tasks/dogfood-runs/2026-05-17-bank-refresh/check_embed_client.py` (resolve project-rag's root via
`machine-local get repos.project_rag`, never a hardcoded drive path). Per anti-scope:
this endpoint is a stopgap project-rag's PM has explicitly declined to make a supported interface
-- the URL lives in exactly one module constant (`PROJECT_RAG_MCP_URL`), there is no retry/backoff
layer, no response-schema mirroring beyond the fields this module actually reads, and no cache.
Every failure -- connection refused, timeout, a non-`ok` verdict -- degrades to a not-measurable
report with a reason; nothing here may raise into a review gate.

THREE FAILURE CAUSES, NAMED APART, NEVER SHARING A WORD. `fetch_duplicate_block_candidates()`
distinguishes:
  (a) `STATIC_NOT_MEASURABLE_DAEMON_UNREACHABLE` -- the daemon did not answer at all: connection
      refused, or the call exceeded project-rag's documented 30s-per-call contract
      (`PROJECT_RAG_CALL_TIMEOUT_S`). Raised by the transport as `ProjectRagTransportError` and
      caught here; never allowed to propagate.
  (b) `STATIC_NOT_MEASURABLE_MISSING_INDEX` -- the tool answered `verdict="missing_index"`: it ran,
      but the vector store was absent or the query raised. The call succeeded; the tool refused.
  (c) is NOT a failure and is measured, not degraded: `verdict="ok"` with `data.unindexed_paths`
      populated means some requested paths carry no chunks and were simply not compared. Quantified
      via `provenance.substrate.paths_requested`/`paths_indexed`, never merely flagged.
A fourth, orthogonal caveat rides beside these three: `provenance.substrate.truncated` marks a query
stage that hit its row cap and silently dropped rows, which means an empty `duplicate_groups`
cannot be reported as measured-clean. `STATIC_NOT_MEASURABLE_TRUNCATED` is its own not-measurable
reason, never folded into (b) -- a truncated call ran and the tool did not refuse it, but the
result is incomplete in a way clean-vs-findings cannot speak to.

`DuplicateBlocksCallResult` carries the raw envelope alongside the classification so C2's
re-verification and C3's per-path four-state report can read `data.duplicate_groups`,
`data.unindexed_paths`, and `provenance.substrate` directly, without this module re-deriving a
parallel shape for fields it does not itself need to inspect.

C2: `reverify_duplicate_groups()` re-reads every candidate member's span from the working tree
and drops a group unless every member's current bytes re-hash (xxh3-64, matching
`indexer/embed.py::_add_chunk_content_hashes`) to the group's own reported `content_hash` --
anchored to what the index reported, never merely to cross-member agreement, so a group whose
members were all mutated identically after the index ran is dropped too. Drops are counted, not
merely flagged: a run that drops everything is a meaningful, reportable outcome, and the count
rides in `ReverifiedDuplicateGroups.dropped_count`. No cache -- re-verification skipped for speed
is exactly the defect the candidate-generator ruling forbids.

C3: `build_static_waste_report()` composes C1's call result and C2's re-verification into a
per-path, four-state report -- `STATIC_PATH_STATUS_MEASURED_CLEAN`,
`STATIC_PATH_STATUS_MEASURED_WITH_FINDINGS`, `STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNREACHABLE`,
`STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNCOVERED`. State (c) from C1 is PER-PATH, not per-report:
one call can measure most of a diff's files and not others, and a single run-level status cannot
say that. A zero is still never inferred from an absence -- measured-and-clean and
could-not-measure remain different facts per path, and the two could-not-measure causes
(whole-call-unreachable vs this-path-was-never-covered) remain distinct from each other.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# Event names this module recognises as a file-open-shaped access. Builtin `open()` delegates
# from `os.open`/`io.open`/`pathlib.Path.open` alike, all of which fire the `open` event itself
# except the two named separately below (measured, not assumed -- see module docstring).
_OPEN_LIKE_EVENTS = frozenset(
    {
        "open",
        "os.open",
        "pathlib.Path.open",
        "pathlib.Path.glob",
        "pathlib.Path.rglob",
        "shutil.copyfile",
        "tempfile.mkstemp",
    }
)

# Confirmed alternate-path opens and the one tell available for a route this module cannot count
# at all (see module docstring's "MEASURED BYPASS ROUTES").
_BYPASS_TELL_EVENTS = frozenset(
    {
        "sqlite3.connect",
        "sqlite3.connect/handle",
        "ctypes.dlsym",
        "ctypes.dlopen",
    }
)

REDUNDANT_OPEN_THRESHOLD = 10
OPENS_PER_QUESTION_THRESHOLD = 100

#: Sibling to `REDUNDANT_OPEN_THRESHOLD` -- bounds the covering-test set
#: `--attribute-diff` runs so a large resolved set cannot silently balloon
#: review-gate cost (the +0.3% affordability measurement covered the hook
#: alone, never a whole covering-test run). The resolved set is sorted by
#: repo-relative POSIX path FIRST, then capped -- an unordered cap would make
#: the attributed number nondeterministic across runs of the same diff, since
#: module-level imports are cached within one process and which tests ran
#: first changes the per-path open count. The emitted `resolved_tests` list is
#: always the exact, capped set actually run, never just a dropped count.
ATTRIBUTION_TEST_CAP = 50

#: Measurement-status vocabulary for `AttributedWasteReport.status` -- a
#: first-class field, never inferred from a zero (module docstring, C1(c)).
MEASUREMENT_STATUS_MEASURED = "measured"
MEASUREMENT_STATUS_NOT_MEASURABLE = "not-measurable"

_REPO_ROOT = Path(__file__).resolve().parents[2]


class _AuditRecorder:
    """Arms exactly one `sys.addaudithook` and counts every event into a plain dict.

    Never logs, prints, or raises from inside `_hook` -- see module docstring's
    "NEVER LOG FROM INSIDE THE HOOK". `sys.addaudithook` cannot be removed once added (CPython
    has no de-registration API), so `disarm()` does not detach the hook -- it flips `_active` to
    False, after which `_hook` returns immediately without touching any counter. The hook stays
    registered for the rest of the interpreter's life; disarming only stops it from recording.
    """

    def __init__(self) -> None:
        self._active = False
        self._armed = False
        self.counts: Dict[str, int] = {}
        self.path_counts: Dict[str, int] = {}

    def _hook(self, event: str, args: Tuple[Any, ...]) -> None:
        if not self._active:
            return
        self.counts[event] = self.counts.get(event, 0) + 1
        if event in _OPEN_LIKE_EVENTS and args:
            try:
                path_key = str(args[0])
            except Exception:
                return
            self.path_counts[path_key] = self.path_counts.get(path_key, 0) + 1

    def arm(self) -> None:
        if self._armed:
            raise RuntimeError("_AuditRecorder.arm() called twice on the same instance")
        self._armed = True
        self._active = True
        sys.addaudithook(self._hook)

    def disarm(self) -> None:
        self._active = False


@dataclass(frozen=True)
class CallRedundancyReport:
    """One live call's full audit-event count, classified into open-like, bypass-tell, and
    unknown buckets -- the last never dropped (module docstring).

    `path_counts` is the per-path open count `measure_call_redundancy` records -- retained here
    (spike verdict Q1b: it was previously discarded at the report boundary, leaving no consumer
    downstream able to attribute anything) so `attribute_redundant_opens()` has a join key against
    a changed-path set. `as_report()` deliberately does NOT dump it wholesale: a full per-path dict
    of an 862-path run is not a reviewer-facing artifact (module docstring). Callers that want the
    raw mapping read `.path_counts` directly, in-process."""

    open_count: int
    unique_paths: int
    redundant_opens: int
    bypass_tells: Dict[str, int]
    unknown_events: Dict[str, int]
    total_events: int
    elapsed_s: float
    path_counts: Dict[str, int] = field(default_factory=dict, repr=False)
    result: Any = field(default=None, repr=False)

    def as_report(self) -> dict:
        return {
            "open_count": self.open_count,
            "unique_paths": self.unique_paths,
            "redundant_opens": self.redundant_opens,
            "bypass_tells": dict(self.bypass_tells),
            "unknown_events": dict(self.unknown_events),
            "total_events": self.total_events,
            "elapsed_s": self.elapsed_s,
        }


def _classify(recorder: _AuditRecorder) -> Tuple[Dict[str, int], Dict[str, int]]:
    bypass_tells: Dict[str, int] = {}
    unknown_events: Dict[str, int] = {}
    for event, count in recorder.counts.items():
        if event in _OPEN_LIKE_EVENTS:
            continue
        if event in _BYPASS_TELL_EVENTS:
            bypass_tells[event] = count
        else:
            unknown_events[event] = count
    return bypass_tells, unknown_events


def measure_call_redundancy(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> CallRedundancyReport:
    """Run `fn(*args, **kwargs)` under one armed audit hook and return the redundancy report.

    Watches ALL audit events (module docstring's HARD CONSTRAINT), not a filter to `open`.
    """
    recorder = _AuditRecorder()
    recorder.arm()
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    finally:
        recorder.disarm()
    elapsed = time.perf_counter() - t0

    open_count = sum(count for event, count in recorder.counts.items() if event in _OPEN_LIKE_EVENTS)
    unique_paths = len(recorder.path_counts)
    redundant_opens = sum(max(0, count - 1) for count in recorder.path_counts.values())
    bypass_tells, unknown_events = _classify(recorder)
    total_events = sum(recorder.counts.values())

    return CallRedundancyReport(
        open_count=open_count,
        unique_paths=unique_paths,
        redundant_opens=redundant_opens,
        bypass_tells=bypass_tells,
        unknown_events=unknown_events,
        total_events=total_events,
        elapsed_s=elapsed,
        path_counts=dict(recorder.path_counts),
        result=result,
    )


class CountingContainer:
    """Wraps a produced container so every `__contains__`/`__iter__`/`__len__` on it is counted
    as one "question" -- the work-vs-question instrument from the spike's Mechanism B, rebuilt for
    keeps. Wrap whatever a suspect function returns, run the real consumer against the wrapper
    instead of the raw value, then read `.query_count`.
    """

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped
        self.query_count = 0

    def __contains__(self, item: Any) -> bool:
        self.query_count += 1
        return item in self._wrapped

    def __iter__(self):
        self.query_count += 1
        return iter(self._wrapped)

    def __len__(self) -> int:
        self.query_count += 1
        return len(self._wrapped)

    def __repr__(self) -> str:
        return f"CountingContainer({self._wrapped!r}, query_count={self.query_count})"


#: Whether this platform's default filesystem is case-insensitive-but-case-preserving (Windows,
#: default macOS/HFS+/APFS) -- both sides of every path-membership comparison below are case-folded
#: when true, mirroring `os.path.normcase`'s own platform split, so a differently-cased caller path
#: still matches a differently-cased audit-recorded path (reviewer Finding 4). Never folded on
#: case-sensitive POSIX filesystems (Linux, most CI), where doing so would wrongly collide two
#: genuinely distinct paths.
_CASE_INSENSITIVE_FS = sys.platform in ("win32", "cygwin", "darwin")


def _case_fold(path: str) -> str:
    return path.lower() if _CASE_INSENSITIVE_FS else path


def _normalize_repo_relative(path: str, repo_root: Optional[Path] = None) -> str:
    """Normalize a caller-supplied changed path to a POSIX-separated, repo-relative string.

    Windows-and-POSIX both (module docstring's path-comparison rule): a caller on Windows may pass
    backslash-separated paths, so the raw string is never compared directly -- `PurePosixPath`
    after a blanket separator swap is the same normalisation `_try_repo_relative` below applies to
    the audit hook's own recorded paths, so both sides of the membership test share one basis. Case
    is folded on case-insensitive filesystems (module docstring's Windows-and-POSIX rule; reviewer
    Finding 4) so a differently-cased caller path still matches a differently-cased recorded path.

    An absolute path is made repo-relative against `repo_root` when supplied and the path resolves
    under it; an absolute path outside `repo_root`, or supplied with no `repo_root` to resolve
    against, is returned normalised-but-unresolved -- it will not match any `_try_repo_relative`
    result (which is always repo-root-relative) and so falls through to `elsewhere_in_repo`/
    `out_of_repo` rather than ever being silently treated as attributable (reviewer Finding 3).
    """
    if Path(path).is_absolute() and repo_root is not None:
        try:
            resolved = Path(path).resolve()
            rel = resolved.relative_to(Path(repo_root).resolve())
            return _case_fold(PurePosixPath(rel.as_posix()).as_posix())
        except (OSError, ValueError):
            pass
    posix_path = PurePosixPath(path.replace("\\", "/"))
    return _case_fold(posix_path.as_posix())


def _try_repo_relative(raw_path: str, repo_root: Path) -> Optional[str]:
    """Resolve one audit-hook-recorded path to a POSIX-separated, repo-relative string, or `None`
    if it resolves outside `repo_root` entirely (stdlib, site-packages, `.pyc`, editable-install
    path hooks -- the 370-of-374 majority the spike measured in a clean run).

    Never raises: a path this module cannot resolve (a synthetic string from a bypass tell, an
    already-relative path resolved against an unexpected cwd) is treated as out-of-repo rather than
    crashing the whole attribution pass. Case-folded on case-insensitive filesystems (reviewer
    Finding 4) to share one basis with `_normalize_repo_relative`.
    """
    try:
        resolved = Path(raw_path).resolve()
    except Exception:
        return None
    try:
        rel = resolved.relative_to(repo_root)
    except ValueError:
        return None
    return _case_fold(PurePosixPath(rel.as_posix()).as_posix())


@dataclass(frozen=True)
class AttributedWasteReport:
    """`attribute_redundant_opens()`'s output -- the diff-attributed view of one
    `CallRedundancyReport`, per the spike's binding conditions.

    `status`/`reason` are the first-class measurement-status field (module docstring, C1(c)):
    `MEASUREMENT_STATUS_NOT_MEASURABLE` is set with a reason string whenever there is nothing to
    attribute against (no changed paths supplied, or -- for `--attribute-diff` -- no covering test
    resolved), never inferred from `attributable_redundant_opens == 0`, which is itself a
    legitimate MEASURED outcome (a clean run).

    `attributable_paths` is ranked (highest redundant-open count first, path as the tie-break) so
    the offending path surfaces at rank 1 with its exact count, matching the spike's own filtered
    measurement. `out_of_repo_redundant_opens` is reported as ONE number, never enumerated (module
    docstring) -- listing 370 stdlib paths is not a reviewer-facing artifact.

    `basis` states in prose what both sides of every threshold comparison against this report's
    `attributable_redundant_opens` are measured on, per the module docstring's BASIS CHECK: this is
    the in-repo redundant-open count filtered to the caller's changed-path set, never the raw
    unfiltered count `CallRedundancyReport.redundant_opens` carries.
    """

    status: str
    reason: Optional[str]
    attributable_redundant_opens: int
    attributable_paths: Tuple[Tuple[str, int], ...]
    elsewhere_in_repo_redundant_opens: int
    out_of_repo_redundant_opens: int
    basis: str

    def as_report(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "attributable_redundant_opens": self.attributable_redundant_opens,
            "attributable_paths": [
                {"path": path, "redundant_opens": count} for path, count in self.attributable_paths
            ],
            "elsewhere_in_repo_redundant_opens": self.elsewhere_in_repo_redundant_opens,
            "out_of_repo_redundant_opens": self.out_of_repo_redundant_opens,
            "basis": self.basis,
        }


_ATTRIBUTION_BASIS = (
    "in-repo redundant opens, filtered to the caller-supplied changed-path set "
    "(never the raw CallRedundancyReport.redundant_opens, which includes stdlib/site-packages/"
    ".pyc/editable-install-hook opens outside the repo)"
)


def attribute_redundant_opens(
    report: CallRedundancyReport,
    repo_root: Path,
    changed_paths: Sequence[str],
) -> AttributedWasteReport:
    """Filter `report.path_counts` to `changed_paths`, per the spike's binding conditions.

    Returns three buckets: redundant opens attributable to `changed_paths`, redundant opens
    elsewhere in the repo, and out-of-repo redundant opens as one count. `changed_paths` and every
    recorded path are compared as `PurePosixPath`-normalised repo-relative strings (module
    docstring's Windows-and-POSIX rule) -- never raw string equality on separators.

    `status` is `MEASUREMENT_STATUS_NOT_MEASURABLE`, with a reason, when `changed_paths` is empty --
    there is nothing to attribute against, which is a different fact from "measured, found
    nothing" (an empty `attributable_paths` with a non-empty `changed_paths`, which is
    `MEASUREMENT_STATUS_MEASURED`).
    """
    repo_root_resolved = Path(repo_root).resolve()
    changed_norm = {_normalize_repo_relative(p, repo_root_resolved) for p in changed_paths}

    attributable: Dict[str, int] = {}
    elsewhere_in_repo = 0
    out_of_repo = 0

    # Precedence, cheapest/most-certain classification first: out-of-repo (a `None` from
    # `_try_repo_relative`) is checked before attributable, which is checked before the
    # elsewhere-in-repo catch-all (reviewer Finding 6). A future fourth bucket should be inserted
    # by name here, not re-derived from the chain's shape.
    for raw_path, count in report.path_counts.items():
        redundant = max(0, count - 1)
        if redundant == 0:
            continue
        rel = _try_repo_relative(raw_path, repo_root_resolved)
        if rel is None:
            out_of_repo += redundant
        elif rel in changed_norm:
            attributable[rel] = attributable.get(rel, 0) + redundant
        else:
            elsewhere_in_repo += redundant

    ranked = tuple(sorted(attributable.items(), key=lambda kv: (-kv[1], kv[0])))
    attributable_total = sum(count for _, count in ranked)

    if not changed_norm:
        return AttributedWasteReport(
            status=MEASUREMENT_STATUS_NOT_MEASURABLE,
            reason="no changed paths supplied -- nothing to attribute against",
            attributable_redundant_opens=0,
            attributable_paths=(),
            elsewhere_in_repo_redundant_opens=elsewhere_in_repo,
            out_of_repo_redundant_opens=out_of_repo,
            basis=_ATTRIBUTION_BASIS,
        )

    return AttributedWasteReport(
        status=MEASUREMENT_STATUS_MEASURED,
        reason=None,
        attributable_redundant_opens=attributable_total,
        attributable_paths=ranked,
        elsewhere_in_repo_redundant_opens=elsewhere_in_repo,
        out_of_repo_redundant_opens=out_of_repo,
        basis=_ATTRIBUTION_BASIS,
    )


@dataclass(frozen=True)
class WasteVerdict:
    """The threshold evaluation against one `CallRedundancyReport`, per the module docstring's
    THRESHOLD DESIGN section. `flagged` is a plain bool; `reasons` names every threshold that
    fired, never just the first."""

    flagged: bool
    reasons: Tuple[str, ...]

    def as_report(self) -> dict:
        return {"flagged": self.flagged, "reasons": list(self.reasons)}


def evaluate_waste(
    report: CallRedundancyReport,
    redundant_opens: int,
    *,
    query_count: Optional[int] = None,
) -> WasteVerdict:
    """Classify against the three named thresholds. `query_count` is optional -- omit it to
    evaluate call redundancy alone (no work-vs-question claim made).

    `redundant_opens` is an EXPLICIT, required argument naming the MEASURAND judged against
    `REDUNDANT_OPEN_THRESHOLD` -- this function does not read `report.redundant_opens` by default.
    Per the module docstring's BASIS CHECK: 10 (the raw-basis threshold) and 13 (the spike's
    measured clean-run floor for the IN-REPO-filtered basis) are BOTH correct numbers, measured on
    different bases, and a caller that lets this function silently pick one risks comparing a
    threshold to the wrong basis without ever seeing the mismatch -- exactly the defect this plan
    fixes. Pass `report.redundant_opens` for the raw, unfiltered single-target basis (`main()`'s
    bare-target mode, where there is no diff to filter against), or an
    `AttributedWasteReport.attributable_redundant_opens` for the diff-filtered basis
    (`--attribute-diff`). A basis error here would always push toward a FALSE GREEN (the raw count
    sits far above the in-repo floor, so accidentally comparing a filtered count against a
    raw-calibrated expectation, or vice versa, tends to under-flag rather than over-flag) -- the
    dangerous direction, because it reads as success and survives repetition.
    """
    reasons = []

    if redundant_opens > REDUNDANT_OPEN_THRESHOLD:
        reasons.append(
            f"redundant_opens={redundant_opens} exceeds REDUNDANT_OPEN_THRESHOLD="
            f"{REDUNDANT_OPEN_THRESHOLD}"
        )

    if query_count is not None:
        if report.open_count > 0 and query_count == 0:
            reasons.append(
                f"open_count={report.open_count} with query_count=0 -- built and never consulted"
            )
        elif query_count > 0:
            ratio = report.open_count / query_count
            if ratio > OPENS_PER_QUESTION_THRESHOLD:
                reasons.append(
                    f"opens_per_question={ratio:.1f} exceeds OPENS_PER_QUESTION_THRESHOLD="
                    f"{OPENS_PER_QUESTION_THRESHOLD}"
                )

    return WasteVerdict(flagged=bool(reasons), reasons=tuple(reasons))


def _resolve_target(target: str) -> Callable[..., Any]:
    """`target` is `module.path:callable_name`, e.g. `coordinator.bin.expired_plan_gates:main`."""
    if ":" not in target:
        raise ValueError(f"target must be 'module.path:callable_name', got {target!r}")
    module_path, _, attr = target.partition(":")
    module = importlib.import_module(module_path)
    fn = getattr(module, attr)
    if not callable(fn):
        raise ValueError(f"{target!r} resolved to a non-callable: {fn!r}")
    return fn


class AttributionError(RuntimeError):
    """A fail-loud precondition for `--attribute-diff`, raised only BEFORE the audit hook could
    arm (engine-root resolution or the naming-convention test-resolver import). `main()` converts
    this to a non-zero exit with the message on stderr -- see module docstring's ATTRIBUTION
    section. Never raised once the hook has armed; a failure after that point degrades to a
    `MEASUREMENT_STATUS_NOT_MEASURABLE` report on stdout with exit 0 instead (`run_attribute_diff`).

    Mirrors `compose-review-wave.py`'s `ComposeError` / `emit-dispatch-workflow.py`'s `EmitError`
    posture for the same `coordinator_core`-unreachable precondition: fail loud, never a silent
    degrade or a reimplemented parallel resolver (staff-eng Finding 2, C1(d))."""


def _ensure_engine_on_path() -> None:
    """Put the engine root on `sys.path`, fail-loud -- the same self-location-first bootstrap
    every other `coordinator/bin/*.py` engine-backed CLI uses (see e.g.
    `coordinator/bin/compose-review-wave.py`). Idempotent: `require_colocated_engine_on_path`
    front-inserts onto `sys.path` and a second call is harmless.

    § Path resolution (docs/plans/2026-09-18-doe-holds-no-scripts.md): `coordinator_core` is
    engine class here -- this module's own tree IS the engine root now, so there is no repo
    boundary left to cross. This replaces the DoE version's `_resolve_engine_root_or_raise`,
    which reached across a repo boundary into claude-klabauter via the DoE-side `_engine_root`
    shim (`coordinator/hooks/scripts/_engine_root.py`); that shim is deleted outright, not
    ported, per the engine-class resolution rule every other moved `coordinator/bin/*.py`
    CLI in this plan follows."""
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)


def _import_test_target_mapper() -> Callable[..., Optional[str]]:
    """Import the private engine binding that resolves a written path to its naming-convention
    test target -- `coordinator_core.ops.dispatch_emit.pathspec._map_written_path_to_test_target`.

    NAMING-CONVENTION RESOLUTION, NOT COVERING-TEST RESOLUTION (see
    docs/plans/2026-08-28-waste-number-reaches-the-reviewer.md chunk C3's body for the full
    rationale this module inherits): `foo.py` maps to `tests/test_foo.py` if that file exists; a
    changed file with no name-matched test resolves to NOTHING, which is a `not-measurable` case,
    never a fabricated zero. Reusing a private (`_`-prefixed) engine binding is a coupling
    decision, so import failure is FAIL LOUD via `AttributionError` -- never a silently
    reimplemented parallel resolver."""
    try:
        _ensure_engine_on_path()
        from coordinator_core.ops.dispatch_emit import pathspec as engine_pathspec
    except Exception as exc:
        raise AttributionError(
            f"coordinator_core.ops.dispatch_emit.pathspec unimportable ({exc}) -- "
            "naming-convention test resolution needs this private engine binding and there is no "
            "local fallback"
        )
    return engine_pathspec._map_written_path_to_test_target  # noqa: SLF001 - engine seam


def _resolve_covering_tests(changed_paths: Sequence[str], repo_root: Path) -> Tuple[str, ...]:
    """Resolve `changed_paths` to their naming-convention test targets, deduplicated, sorted by
    repo-relative POSIX path, and capped at `ATTRIBUTION_TEST_CAP` (see that constant's docstring
    for why the sort must precede the cap -- determinism across runs of the same diff)."""
    mapper = _import_test_target_mapper()
    targets: set = set()
    for path in changed_paths:
        target = mapper(path, repo_root=repo_root)
        if target is not None:
            targets.add(target)
    ordered = tuple(sorted(targets, key=lambda p: PurePosixPath(p).as_posix()))
    return ordered[:ATTRIBUTION_TEST_CAP]


def _static_attribution_section(
    normalized_changed: Sequence[str],
    root: Path,
    static_transport: Any,
) -> dict:
    """Compute the static (duplicate-block) section to nest under `attribution["static"]`.

    Runs independently of `resolved_tests`/`AttributionError` (C1's sequencing statement, C3b): a
    peer of the dynamic signal, not its child, computed and emitted on every leg of
    `run_attribute_diff`, including a changed-path set that resolves zero covering tests. Never
    raises -- `fetch_duplicate_block_candidates`/`build_static_waste_report` already degrade every
    failure to a not-measurable report with a reason (module docstring's degrade-never-raise rule).
    """
    fetch_result = fetch_duplicate_block_candidates(
        normalized_changed, scope="corpus", transport=static_transport
    )
    static_report = build_static_waste_report(fetch_result, normalized_changed, repo_root=root)
    return static_report.as_report()


def run_attribute_diff(
    changed_paths: Sequence[str],
    repo_root: Optional[Path] = None,
    static_transport: Any = None,
) -> dict:
    """The `--attribute-diff` mechanism: resolve covering tests for `changed_paths` by naming
    convention, arm the audit hook, run the resolved tests in ONE child process via `pytest.main()`,
    and attribute the redundant opens back to `changed_paths` via `attribute_redundant_opens`. Also
    computes the static duplicate-block signal (C1-C3) and nests it under `attribution["static"]`
    on all three legs (C3b) -- never as a sibling top-level key, so it survives
    `_run_waste_attribution`'s `parsed.get("attribution")` filter in `compose-review-wave.py`.

    Raises `AttributionError` only for a pre-arm failure (engine/import resolution) -- `main()`
    converts that to a non-zero exit. Every other failure (no covering test resolved, the covering
    -test run itself crashing) is caught here and returned as a `MEASUREMENT_STATUS_NOT_MEASURABLE`
    report instead, per module docstring: a reviewer must be able to tell "measured, found nothing"
    from "could not measure," and a crash must never surface as a dead review gate.

    `static_transport` is test-only injection (mirrors `fetch_duplicate_block_candidates`'s own
    `transport` parameter) -- `None` uses the real daemon transport.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    normalized_changed = [_normalize_repo_relative(p, root) for p in changed_paths]
    resolved_tests = _resolve_covering_tests(normalized_changed, root)  # pre-arm; may raise

    if not resolved_tests:
        attribution = AttributedWasteReport(
            status=MEASUREMENT_STATUS_NOT_MEASURABLE,
            reason="no covering test resolved by naming convention for any changed path",
            attributable_redundant_opens=0,
            attributable_paths=(),
            elsewhere_in_repo_redundant_opens=0,
            out_of_repo_redundant_opens=0,
            basis=_ATTRIBUTION_BASIS,
        ).as_report()
        attribution["static"] = _static_attribution_section(normalized_changed, root, static_transport)
        return {
            "changed_paths": normalized_changed,
            "resolved_tests": [],
            "report": None,
            "attribution": attribution,
        }

    import pytest  # local import: only --attribute-diff needs pytest, not the base module

    crash_reason: List[str] = []

    def _run() -> Optional[int]:
        try:
            return pytest.main(list(resolved_tests))
        except BaseException as exc:  # hook is armed; a crash here must degrade, never propagate
            crash_reason.append(f"{type(exc).__name__}: {exc}")
            return None

    report = measure_call_redundancy(_run)

    if crash_reason:
        attribution = AttributedWasteReport(
            status=MEASUREMENT_STATUS_NOT_MEASURABLE,
            reason=f"covering-test run crashed: {crash_reason[0]}",
            attributable_redundant_opens=0,
            attributable_paths=(),
            elsewhere_in_repo_redundant_opens=0,
            out_of_repo_redundant_opens=0,
            basis=_ATTRIBUTION_BASIS,
        ).as_report()
        attribution["static"] = _static_attribution_section(normalized_changed, root, static_transport)
        return {
            "changed_paths": normalized_changed,
            "resolved_tests": list(resolved_tests),
            "report": report.as_report(),
            "attribution": attribution,
        }

    attribution = attribute_redundant_opens(report, root, normalized_changed).as_report()
    attribution["static"] = _static_attribution_section(normalized_changed, root, static_transport)
    return {
        "changed_paths": normalized_changed,
        "resolved_tests": list(resolved_tests),
        "report": report.as_report(),
        "attribution": attribution,
    }


#: Direct daemon port. Stopgap per module docstring's THE STATIC SIGNAL section -- lives in this
#: one module constant, no retry/backoff layer, no cache.
PROJECT_RAG_MCP_URL = "http://127.0.0.1:8767/mcp"

#: project-rag's own documented per-call contract (module docstring, cause (a)).
PROJECT_RAG_CALL_TIMEOUT_S = 30

#: The three failure causes, named apart, never sharing a word (module docstring). Cause (c) --
#: `unindexed_paths` -- is deliberately NOT a member of this set: it is a measured, partial-success
#: outcome, not a not-measurable one.
STATIC_NOT_MEASURABLE_DAEMON_UNREACHABLE = "daemon-unreachable"
STATIC_NOT_MEASURABLE_MISSING_INDEX = "missing-index"
STATIC_NOT_MEASURABLE_TRUNCATED = "truncated"
#: The re-verification hasher is unavailable (`xxhash` not importable). Its own reason, never
#: folded into (b): "the index was absent" and "we could not check what the index returned" are
#: different facts about different halves of the mechanism, and the remedy differs -- reindex vs
#: install a dependency. Reusing (b)'s word here would be the same-word collision the THREE FAILURE
#: CAUSES section forbids.
STATIC_NOT_MEASURABLE_REVERIFY_UNAVAILABLE = "reverify-unavailable"


class ProjectRagTransportError(Exception):
    """Raised by a transport's `call_tool()` when the daemon could not be reached at all --
    connection refused, or the call exceeded `PROJECT_RAG_CALL_TIMEOUT_S`. Distinct from a
    tool-level `missing_index` verdict, which means the call succeeded and the *tool itself*
    refused (module docstring, cause (a) vs (b)). Caught by `fetch_duplicate_block_candidates()`
    and never allowed to propagate into a review gate."""


class _HttpStreamableTransport:
    """JSON-RPC-over-streamable-HTTP transport against `PROJECT_RAG_MCP_URL`: `initialize` ->
    `notifications/initialized` -> `tools/call`, from a plain subprocess/process -- no MCP client
    harness. Mirrors project-rag's own
    `tasks/dogfood-runs/2026-05-17-bank-refresh/check_embed_client.py` transport shape, proven by
    execution this session. Session id and request id are per-instance state, matching that
    reference client's module-level globals.

    Tests never exercise this class directly -- `fetch_duplicate_block_candidates()` accepts an
    injectable `transport` (any object exposing `call_tool(name, arguments) -> dict`), and the
    fake transports used in tests implement that same narrow interface without touching a socket.
    """

    def __init__(self, url: str = PROJECT_RAG_MCP_URL, timeout: float = PROJECT_RAG_CALL_TIMEOUT_S) -> None:
        self._url = url
        self._timeout = timeout
        self._session_id: Optional[str] = None
        self._req_id = 0
        self._initialized = False

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _call(self, method: str, params: dict) -> Optional[dict]:
        import urllib.error
        import urllib.request

        req_id = self._next_id()
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(self._url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                body = resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ProjectRagTransportError(f"{type(exc).__name__}: {exc}") from exc

        result = None
        for line in body.splitlines():
            if line.startswith("data: "):
                try:
                    msg = json.loads(line[len("data: "):])
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == req_id:
                    result = msg.get("result")
        if result is None:
            try:
                msg = json.loads(body)
            except json.JSONDecodeError:
                msg = None
            if isinstance(msg, dict) and msg.get("id") == req_id:
                result = msg.get("result")
        return result

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "waste-signal", "version": "1.0"},
            },
        )
        self._call("notifications/initialized", {})
        self._initialized = True

    def call_tool(self, name: str, arguments: dict) -> dict:
        self._ensure_initialized()
        result = self._call("tools/call", {"name": name, "arguments": arguments})
        if not result:
            raise ProjectRagTransportError("empty or malformed tools/call response")
        for block in result.get("content", []) or []:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except json.JSONDecodeError as exc:
                    raise ProjectRagTransportError(f"non-JSON tool response text: {exc}") from exc
        raise ProjectRagTransportError("tools/call response carried no text content block")


@dataclass(frozen=True)
class DuplicateBlocksCallResult:
    """One `fetch_duplicate_block_candidates()` call, classified per the module docstring's THREE
    FAILURE CAUSES section. `status` is the same `MEASUREMENT_STATUS_MEASURED`/
    `MEASUREMENT_STATUS_NOT_MEASURABLE` vocabulary the dynamic signal already uses
    (waste-signal.py:142-143) -- extended here to the static signal, not replaced.

    `not_measurable_reason` is one of `STATIC_NOT_MEASURABLE_DAEMON_UNREACHABLE`,
    `STATIC_NOT_MEASURABLE_MISSING_INDEX`, or `STATIC_NOT_MEASURABLE_TRUNCATED` when `status` is
    `MEASUREMENT_STATUS_NOT_MEASURABLE`; `None` when measured. Cause (c) (`unindexed_paths`) never
    sets this field -- it is carried on `response["data"]["unindexed_paths"]` on an otherwise
    MEASURED result, per the module docstring's "(c) is NOT a failure" ruling.

    `response` is the raw project_duplicate_blocks envelope (or `None` on a transport failure) --
    kept whole, not re-mirrored into a parallel shape, so C2's re-verification and C3's per-path
    report can read `data.duplicate_groups`/`data.unindexed_paths`/`provenance.substrate` directly.
    """

    status: str
    not_measurable_reason: Optional[str]
    hint: Optional[str]
    response: Optional[dict]

    def as_report(self) -> dict:
        return {
            "status": self.status,
            "not_measurable_reason": self.not_measurable_reason,
            "hint": self.hint,
        }


def _classify_duplicate_blocks_envelope(envelope: dict) -> DuplicateBlocksCallResult:
    """Classify an already-received `project_duplicate_blocks` envelope. Never raises -- an
    envelope shape this module does not recognise degrades to not-measurable rather than crashing
    a review gate (module docstring)."""
    verdict = envelope.get("verdict") if isinstance(envelope, dict) else None

    if verdict == "missing_index":
        provenance = envelope.get("provenance") or {}
        hint = envelope.get("hint") or provenance.get("hint")
        return DuplicateBlocksCallResult(
            status=MEASUREMENT_STATUS_NOT_MEASURABLE,
            not_measurable_reason=STATIC_NOT_MEASURABLE_MISSING_INDEX,
            hint=hint,
            response=envelope,
        )

    if verdict == "ok":
        data = envelope.get("data") or {}
        provenance = envelope.get("provenance") or {}
        substrate = provenance.get("substrate") or {}
        truncated = bool(data.get("truncated") or substrate.get("truncated"))
        if truncated:
            return DuplicateBlocksCallResult(
                status=MEASUREMENT_STATUS_NOT_MEASURABLE,
                not_measurable_reason=STATIC_NOT_MEASURABLE_TRUNCATED,
                hint=envelope.get("hint"),
                response=envelope,
            )
        # Cause (c) -- unindexed_paths -- is not a failure and does not set
        # not_measurable_reason; it rides on response["data"]["unindexed_paths"] on an
        # otherwise-measured result (module docstring).
        return DuplicateBlocksCallResult(
            status=MEASUREMENT_STATUS_MEASURED,
            not_measurable_reason=None,
            hint=envelope.get("hint"),
            response=envelope,
        )

    # Any other verdict (e.g. input_invalid -- a caller-side bug, not a coverage fact) degrades to
    # not-measurable rather than raising into a review gate. Not one of the three named causes,
    # but distinct in its reason text so it is never mistaken for (a) or (b).
    return DuplicateBlocksCallResult(
        status=MEASUREMENT_STATUS_NOT_MEASURABLE,
        not_measurable_reason=STATIC_NOT_MEASURABLE_MISSING_INDEX,
        hint=envelope.get("hint") if isinstance(envelope, dict) else None,
        response=envelope if isinstance(envelope, dict) else None,
    )


def fetch_duplicate_block_candidates(
    paths: Sequence[str],
    *,
    scope: str = "corpus",
    transport: Any = None,
) -> DuplicateBlocksCallResult:
    """Call project-rag's `project_duplicate_blocks` over `paths` and classify the result per the
    module docstring's THREE FAILURE CAUSES section. `scope="corpus"` per the PM's ruling -- the
    reviewer-relevant finding is "this block already exists elsewhere in the corpus", not merely
    within the diff's own file set.

    `transport` defaults to `_HttpStreamableTransport()` (the real daemon call); tests inject a
    fake exposing `call_tool(name, arguments) -> dict` to drive each of the three response shapes
    without a socket. A transport that raises `ProjectRagTransportError` -- the daemon did not
    answer at all -- classifies as cause (a); every other outcome is classified from the returned
    envelope. Never raises: this is a candidate generator feeding a review gate (module docstring).
    """
    xport = transport if transport is not None else _HttpStreamableTransport()
    try:
        envelope = xport.call_tool("project_duplicate_blocks", {"paths": list(paths), "scope": scope})
    except ProjectRagTransportError as exc:
        return DuplicateBlocksCallResult(
            status=MEASUREMENT_STATUS_NOT_MEASURABLE,
            not_measurable_reason=STATIC_NOT_MEASURABLE_DAEMON_UNREACHABLE,
            hint=f"project-rag daemon unreachable: {exc}",
            response=None,
        )
    return _classify_duplicate_blocks_envelope(envelope)


@dataclass(frozen=True)
class ReverifiedDuplicateGroups:
    """`reverify_duplicate_groups()`'s output -- the candidate-generator ruling this plan exists
    to enforce (module docstring's THE STATIC SIGNAL section), applied.

    `groups` is the subset of the input `duplicate_groups` that survived re-verification against
    the working tree, in their original order. `dropped_count` is the number of groups dropped,
    never inferred by a caller diffing lengths -- a drop is the mechanism working, not an error,
    and is reported as a first-class count. `dropped_groups` retains the dropped groups themselves
    (never just a bare count) so a caller building a per-path report (C3) can still see which
    paths' candidates were dropped and why the count is nonzero.
    """

    groups: Tuple[dict, ...]
    dropped_count: int
    dropped_groups: Tuple[dict, ...]
    #: False when `xxhash` is not importable, so NOTHING was verified. Distinct from an empty
    #: `groups` with `hasher_available=True`, which means every candidate WAS checked and none
    #: survived. Conflating the two is the "zero inferred from an absence" error this module
    #: forbids: one is a measured clean result, the other is a not-measurable call.
    hasher_available: bool = True

    def as_report(self) -> dict:
        return {
            "duplicate_groups": list(self.groups),
            "dropped_count": self.dropped_count,
        }


def _read_span_text(repo_root: Path, rel_path: Any, line_start: Any, line_end: Any) -> Optional[str]:
    """Re-read one reported group member's span from the working tree, 1-indexed inclusive
    (`line_start`/`line_end` as `project_duplicate_blocks` reports them), joined with `\\n`.

    Returns `None` -- never raises -- when the path or span cannot be read: a missing file, a
    span past end-of-file, an unreadable encoding, or a malformed `line_start`/`line_end` are all
    treated identically as "this member cannot be reverified", which `reverify_duplicate_groups`
    treats as a drop rather than a crash into a review gate (module docstring's degrade-never-raise
    rule, extended to the static signal).
    """
    if not isinstance(rel_path, str) or not rel_path:
        return None
    try:
        start = int(line_start)
        end = int(line_end)
    except (TypeError, ValueError):
        return None
    if start < 1 or end < start:
        return None
    try:
        full_path = (Path(repo_root) / rel_path).resolve()
        lines = full_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    start_idx = start - 1
    if start_idx >= len(lines):
        return None
    span = lines[start_idx:end]
    if not span:
        return None
    return "\n".join(span)


def _hash_span_text(text: str) -> Optional[str]:
    """xxh3-64 hex digest of `text`, matching `indexer/embed.py::_add_chunk_content_hashes`'s own
    algorithm (project-rag, `xxhash.xxh3_64_hexdigest(text.encode("utf-8"))`) -- the same digest
    stamped into `content_hash` at index time, so a re-read span can be compared against it
    directly. Local import: only re-verification needs `xxhash`, not the base module (mirrors this
    module's existing `import pytest` local-import convention for `--attribute-diff`).

    Returns `None` -- never raises -- when `xxhash` is not importable. It is NOT declared in this
    repo's dependency surface, so its absence is an ordinary environment state, not an anomaly, and
    an unguarded import here would raise `ModuleNotFoundError` straight through
    `reverify_duplicate_groups` and `build_static_waste_report` into a review gate: precisely the
    failure this module's degrade-never-raise rule exists to prevent, in the code that implements
    it. Callers must treat `None` as "cannot verify at all" and report the whole call
    not-measurable -- never as a per-member mismatch, which would drop every group and render as
    "the index was stale about everything" when the truth is that nothing was checked."""
    try:
        import xxhash
    except ImportError:
        return None

    return xxhash.xxh3_64_hexdigest(text.encode("utf-8"))


def reverify_duplicate_groups(
    duplicate_groups: Sequence[dict],
    repo_root: Path,
) -> ReverifiedDuplicateGroups:
    """Re-read every candidate group's members from the working tree and drop any group whose
    current on-disk bytes no longer agree with the group's OWN reported `content_hash` --
    the standing ruling this plan exists to honour (module docstring's THE STATIC SIGNAL section):
    nothing `project_duplicate_blocks` returns reaches a reviewer unverified against the working
    tree.

    A group survives only when EVERY member's current span, re-hashed with the same xxh3-64
    algorithm the index stamped, matches the group's reported `content_hash`. This anchors to what
    the index reported, not merely to cross-member agreement: a group whose members all agree with
    each other but no longer match the reported hash (e.g. every member mutated identically after
    the index ran) is still dropped, because unanimous is not the same fact as verified. A member
    that cannot be read at all (deleted file, span past end-of-file) is treated as a mismatch, not
    skipped -- an unreadable member cannot be verified, so its group cannot be reported as
    verified. An empty `members` list is also dropped -- there is nothing to have verified.

    Never raises: every per-member read failure degrades to "this member does not verify" rather
    than propagating, consistent with the rest of this module's degrade-never-raise-into-a-
    review-gate rule.
    """
    repo_root_resolved = Path(repo_root).resolve()
    survivors: List[dict] = []
    dropped: List[dict] = []

    # Probe the hasher ONCE, before any group is judged. `_hash_span_text` returns None when
    # `xxhash` is absent, and folding that into the per-member comparison below would mark every
    # member a mismatch and drop every group -- reporting "the index was stale about all of it"
    # when nothing was verified at all. `hasher_available=False` is a whole-call not-measurable
    # condition that the caller reports as such; it is never a finding.
    if _hash_span_text("") is None:
        return ReverifiedDuplicateGroups(
            groups=(),
            dropped_count=0,
            dropped_groups=(),
            hasher_available=False,
        )

    for group in duplicate_groups:
        expected_hash = group.get("content_hash") if isinstance(group, dict) else None
        members = (group.get("members") or []) if isinstance(group, dict) else []
        verified = bool(members) and expected_hash is not None
        for member in members:
            text = _read_span_text(
                repo_root_resolved,
                member.get("path") if isinstance(member, dict) else None,
                member.get("line_start") if isinstance(member, dict) else None,
                member.get("line_end") if isinstance(member, dict) else None,
            )
            if text is None or _hash_span_text(text) != expected_hash:
                verified = False
                break
        if verified:
            survivors.append(group)
        else:
            dropped.append(group)

    return ReverifiedDuplicateGroups(
        groups=tuple(survivors),
        dropped_count=len(dropped),
        dropped_groups=tuple(dropped),
    )


#: Per-path state vocabulary for `StaticWasteReport.per_path` (C3, module docstring's THE STATIC
#: SIGNAL section). Four states, never collapsed to a run-level status: a call can measure some of
#: a diff's paths and not others (C1's cause (c), `unindexed_paths`, is per-path), so "the signal
#: ran" and "your file was checked" are different claims and this module answers both separately.
#: The two COULD_NOT_MEASURE states are never merged into one word: UNREACHABLE covers a whole-call
#: failure (any of C1's three causes -- daemon-unreachable, missing-index, or truncated -- all mean
#: nothing was compared for ANY requested path) while UNCOVERED is per-path even on an otherwise
#: MEASURED call (cause (c) alone, or a path this module never asked about).
STATIC_PATH_STATUS_MEASURED_CLEAN = "measured-and-clean"
STATIC_PATH_STATUS_MEASURED_WITH_FINDINGS = "measured-with-findings"
STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNREACHABLE = "could-not-measure-index-unreachable"
STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNCOVERED = "could-not-measure-index-did-not-cover-path"

#: Sibling to `_ATTRIBUTION_BASIS` (waste-signal.py, dynamic-signal section), in the same prose
#: register: states what both sides of the static signal's per-path comparison are measured on.
#: The dynamic basis compares two counts taken from the SAME live process, in the SAME instant --
#: the static basis does not have that luxury. One side is project-rag's index, built at whatever
#: time the daemon last (re)indexed; the other is the working tree re-read live by
#: `reverify_duplicate_groups` at report time. A group surviving re-verification means both sides
#: agreed at read time, never that the index is current -- a change landing between index time and
#: read time that happens to preserve byte-identity at the reported span would still verify. This
#: is the freshness gap `state/audits/2026-08-27-static-waste-signal-disposition.md` already names
#: and ratifies as a standing limit, not one this module claims to have closed.
_STATIC_ATTRIBUTION_BASIS = (
    "per-path re-verified duplicate-block membership: project-rag's index (built at its own last "
    "indexing time) filtered to duplicate groups whose members' current on-disk bytes, re-read and "
    "re-hashed at report time, still match the group's own reported content_hash -- never "
    "cross-member agreement alone, and never a claim the index itself is current"
)


@dataclass(frozen=True)
class StaticWasteReport:
    """C3's per-path, four-state view of one static-signal run -- `fetch_duplicate_block_candidates`
    (C1) plus `reverify_duplicate_groups` (C2), composed. `per_path` maps every path this module
    was asked about (repo-relative POSIX, case-folded per this module's Windows-and-POSIX rule) to
    one of the four `STATIC_PATH_STATUS_*` states, each entry never a bare word: a not-measurable
    entry always carries a `reason` from C1's `STATIC_NOT_MEASURABLE_*`/cause-(c) vocabulary, and a
    measured-with-findings entry always carries the surviving group(s) that named it.

    Preserves the invariant this whole plan exists to hold: a zero is never inferred from an
    absence. A path missing from `duplicate_groups` because it was never compared
    (`could-not-measure-index-did-not-cover-path`) is a categorically different fact from a path
    compared and found to carry no duplicate (`measured-and-clean`), and this shape can say both
    apart, per-path, in one run.
    """

    per_path: Dict[str, dict]
    duplicate_groups: Tuple[dict, ...]
    dropped_count: int
    call_status: str
    call_not_measurable_reason: Optional[str]
    hint: Optional[str]
    basis: str

    def as_report(self) -> dict:
        return {
            "per_path": self.per_path,
            "duplicate_groups": list(self.duplicate_groups),
            "dropped_count": self.dropped_count,
            "call_status": self.call_status,
            "call_not_measurable_reason": self.call_not_measurable_reason,
            "hint": self.hint,
            "basis": self.basis,
        }


def build_static_waste_report(
    fetch_result: DuplicateBlocksCallResult,
    requested_paths: Sequence[str],
    repo_root: Optional[Path] = None,
) -> StaticWasteReport:
    """Compose C1's call result and C2's re-verification into the per-path, four-state report
    (module docstring's THE STATIC SIGNAL section; C3). Never raises -- every branch here mirrors
    this module's degrade-never-raise-into-a-review-gate rule, extended from the call/re-verify
    layers it composes.

    Whole-call not-measurable (any of C1's three causes) marks EVERY requested path
    `STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNREACHABLE` -- nothing was compared for any of them, so
    there is nothing per-path to say. A MEASURED call still marks a path
    `STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNCOVERED` when it rides in `data.unindexed_paths` (cause
    (c)) or was simply never returned as indexed at all -- both mean "not compared," which this
    module never conflates with "compared, found nothing" (`STATIC_PATH_STATUS_MEASURED_CLEAN`).
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    normalized_requested = [_normalize_repo_relative(p, root) for p in requested_paths]

    if fetch_result.status == MEASUREMENT_STATUS_NOT_MEASURABLE:
        per_path = {
            path: {
                "status": STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNREACHABLE,
                "reason": fetch_result.not_measurable_reason,
            }
            for path in normalized_requested
        }
        return StaticWasteReport(
            per_path=per_path,
            duplicate_groups=(),
            dropped_count=0,
            call_status=fetch_result.status,
            call_not_measurable_reason=fetch_result.not_measurable_reason,
            hint=fetch_result.hint,
            basis=_STATIC_ATTRIBUTION_BASIS,
        )

    response = fetch_result.response or {}
    data = response.get("data") or {}
    raw_groups = data.get("duplicate_groups") or []
    unindexed = {_normalize_repo_relative(p, root) for p in (data.get("unindexed_paths") or [])}

    reverified = reverify_duplicate_groups(raw_groups, root)

    # The candidate generator answered, but nothing it returned could be re-verified against the
    # working tree. The standing ruling is that an unverified candidate never reaches a reviewer,
    # so the only honest report is a whole-call not-measurable -- NOT an empty findings set, which
    # would render as measured-and-clean off candidates nobody checked.
    if not reverified.hasher_available:
        return StaticWasteReport(
            per_path={
                path: {
                    "status": STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNREACHABLE,
                    "reason": STATIC_NOT_MEASURABLE_REVERIFY_UNAVAILABLE,
                }
                for path in normalized_requested
            },
            duplicate_groups=(),
            dropped_count=0,
            call_status=MEASUREMENT_STATUS_NOT_MEASURABLE,
            call_not_measurable_reason=STATIC_NOT_MEASURABLE_REVERIFY_UNAVAILABLE,
            hint=fetch_result.hint,
            basis=_STATIC_ATTRIBUTION_BASIS,
        )

    findings_by_path: Dict[str, List[dict]] = {}
    for group in reverified.groups:
        for member in group.get("members") or []:
            member_path = member.get("path") if isinstance(member, dict) else None
            if not isinstance(member_path, str) or not member_path:
                continue
            rel = _normalize_repo_relative(member_path, root)
            findings_by_path.setdefault(rel, []).append(group)

    per_path = {}
    for path in normalized_requested:
        if path in unindexed:
            per_path[path] = {
                "status": STATIC_PATH_STATUS_COULD_NOT_MEASURE_UNCOVERED,
                "reason": "unindexed_paths",
            }
        elif path in findings_by_path:
            per_path[path] = {
                "status": STATIC_PATH_STATUS_MEASURED_WITH_FINDINGS,
                "duplicate_groups": findings_by_path[path],
            }
        else:
            per_path[path] = {"status": STATIC_PATH_STATUS_MEASURED_CLEAN}

    return StaticWasteReport(
        per_path=per_path,
        duplicate_groups=reverified.groups,
        dropped_count=reverified.dropped_count,
        call_status=fetch_result.status,
        call_not_measurable_reason=fetch_result.not_measurable_reason,
        hint=fetch_result.hint,
        basis=_STATIC_ATTRIBUTION_BASIS,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="waste-signal",
        description=(
            "Dynamic, opt-in reviewer's instrument: counts file-open-shaped audit events for one "
            "live-executed callable and reports call redundancy against a named, revisable "
            "threshold. NOT a security control -- see module docstring."
        ),
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Importable target as 'module.path:callable_name', called with no arguments. "
            "Mutually exclusive with --attribute-diff."
        ),
    )
    parser.add_argument(
        "--attribute-diff",
        nargs="+",
        metavar="PATH",
        default=None,
        help=(
            "Repo-relative changed paths. Resolves their covering tests by naming convention, "
            "runs them in-process under the audit hook, and prints the attributed report as JSON "
            "on stdout. Mutually exclusive with a bare target."
        ),
    )
    parser.add_argument("--out", type=str, default=None, help="Write JSON report here instead of stdout")
    return parser


def _emit(text: str, out: Optional[str]) -> None:
    if out is not None:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.attribute_diff is not None:
        if args.target is not None:
            print("waste-signal: --attribute-diff and a target are mutually exclusive", file=sys.stderr)
            return 2
        try:
            rendered = run_attribute_diff(args.attribute_diff)
        except AttributionError as exc:
            print(f"waste-signal --attribute-diff: {exc}", file=sys.stderr)
            return 1
        _emit(json.dumps(rendered, indent=2), args.out)
        return 0

    if args.target is None:
        print("waste-signal: a target is required unless --attribute-diff is given", file=sys.stderr)
        return 2

    fn = _resolve_target(args.target)
    report = measure_call_redundancy(fn)
    verdict = evaluate_waste(report, report.redundant_opens)
    rendered = {
        "target": args.target,
        "report": report.as_report(),
        "verdict": verdict.as_report(),
    }
    _emit(json.dumps(rendered, indent=2), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
