"""red-set-report.py — derive the red-cell census for a pytest path, never assert it.

Spec backlink: pln-make-the-bash-guards-suite-a-g-2f81d6 § C1b

WHY THIS EXISTS
    `docs/reference/test-tiers.md`'s hand-maintained prose figures went stale
    twice, and once caused a triage to wrongly write off 45 gating failures as
    an "unwired" corpus. This script never hardcodes a number.

    C1b FIX (was: diff two EXECUTION runs). The original approach ran pytest
    twice -- unfiltered, then under the fast-tier marker expression -- and
    diffed the two FAILURE sets, attributing the difference to marker
    exclusion. That inference is invalid in a shared working tree: the two
    runs are minutes apart, and a transient failure present in one and absent
    from the other gets silently counted as marker-excluded. C8 measured this
    happening (~40 cells derived as marker-excluded against only 2 marker
    decorators in the whole tree). Marker membership is a STATIC property of
    the tree, not an outcome -- so it is now derived from two `--collect-only`
    passes (`collected_all`, `collected_fast`), which execute nothing and
    cannot be perturbed by a peer's concurrent edit. `marked = collected_all -
    collected_fast` is then exact and deterministic. Exactly ONE execution
    pass (unfiltered) supplies `failed_all`; `unmarked_failed = failed_all &
    collected_fast`. This also removes an entire execution pass.

WHAT IT EMITS
    A JSON object on stdout (machine-readable; C8 consumes `unmarked_failed`
    at runtime to seed a nodeid-SET ratchet) plus one human-readable summary
    line on stderr, so `... | jq` style piping stays clean.

MARKER EXPRESSION / TESTPATHS
    Read live from pyproject.toml's [tool.pytest.ini_options] (`markers`,
    `testpaths`) -- never hardcoded here, because both drift (see WHY above).
    The fast-tier expression itself, `not cadence and not pending_fix and not
    designed_red`, is the one figure this script's caller may pass via
    --marker-expr; the default matches the tri-marker set actually declared
    in pyproject.toml today.

WORKER CAP
    HARD CONSTRAINT: never bare `-n auto` -- unbounded parallel pytest-xdist
    workers have killed a session on this box before. Default is serial (no
    -n flag at all); --workers N caps explicitly, and the cap is clamped to
    min(physical_cores // 2, usable_ram_mb // 150) when --workers exceeds it.

NEGATIVE SPEC
    - Does not gate on any number -- it reports; a caller decides pass/fail.
    - Does not read or write state/bash-guards/known-red.json (that ratchet
      file is C8's, a later chunk in the same plan).
    - Does not shell out to bash; the only subprocess spawned is
      `python -m pytest` itself. No third-party report plugin (e.g.
      pytest-json-report) is required -- outcome counts and node-id sets are
      read from `terminalreporter.stats` via a small in-process collector
      plugin using pytest/_pytest hooks only.
    - Does not infer marker membership from execution outcome (C1b) -- the
      marked/unmarked split comes from two `--collect-only` passes, never
      from diffing two runs' failure sets.
    - Does not silently trust that the tree held still across its two
      `--collect-only` subprocess calls -- asserts `collected_fast` is a
      subset of `collected_all` and fails loudly, naming the offending
      node-ids, if a peer's concurrent commit violates that invariant. Also
      reports the git HEAD SHA before and after the whole measurement so a
      caller can see whether the tree moved.
    - Never treats an empty collected-test count as a passing/silent result
      (ported from the DoE-plane fork's denominator assertion, W3-C5,
      `docs/plans/2026-09-18-doe-holds-no-scripts.md`) -- a `target` that
      collects zero tests raises `ValueError` rather than reporting a
      vacuously green (0 collected, 0 failed) census.

SECOND TOOL, SAME FILE (superset of the DoE-plane red-set-report)
    Two verb families share this module and never overlap. Bare
    `red-set-report.py <target> [--marker-expr E] [--workers N]` is the
    marked/unmarked census above. `red-set-report.py [--repo-root R] observed
    --entry NAME` and `... count --registry FILE` are the ceremony_test_cmds
    verbs DoE's `coordinator/tests/test_known_red_ratchet.py` consumes via
    `derive_observed_red`, `derive_known_red_count`, `resolve_entry`,
    `guard_not_nested`, `assert_no_self_containment`, `run_pytest_observe`.
    Those run pytest as a child process with an itemcollected/logreport plugin
    and never scrape stdout. `main(argv)` takes argv WITHOUT the program name.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

DEFAULT_MARKER_EXPR = "not cadence and not pending_fix and not designed_red"

GENERATES = []  # every write (plugin source, report.json) lands under tempfile.TemporaryDirectory() per run_pytest_collect/run_pytest_json — no tracked artifact

# Re-entrancy sentinel (P0 belt-and-braces). `derive_red_set`'s unfiltered
# execution pass (`run_pytest_json(..., marker_expr=None, ...)`) applies NO
# marker filter, so if this script's own target tree ever contains a test
# cell that itself shells out to this script (as a self-referential ratchet
# test would), that nested pytest invocation would re-execute the same cell,
# which spawns another red-set-report.py subprocess against the same target,
# unbounded. `test_known_red_ratchet.py` was moved to `coordinator_core/tests/`
# specifically to not be that cell -- this sentinel is the second layer, so a
# FUTURE test landing back inside the measured tree fails loudly instead of
# recursing to exhaustion.
_REENTRANCY_ENV_VAR = "COORDINATOR_RED_SET_REPORT_ACTIVE"


def load_pytest_config(pyproject_path: Path = PYPROJECT_PATH) -> dict:
    """Read `[tool.pytest.ini_options]` off pyproject.toml -- never off prose."""
    raw = pyproject_path.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    return data.get("tool", {}).get("pytest", {}).get("ini_options", {})


def declared_markers(pytest_config: dict) -> list[str]:
    """Marker names declared in `markers = [...]`, stripped of their `: desc` suffix."""
    names = []
    for entry in pytest_config.get("markers", []):
        name = entry.split(":", 1)[0].strip()
        if name:
            names.append(name)
    return names


# The fast-tier gate names -- the subset of declared markers that partition
# the suite into "runs per-commit" vs "excluded from the fast tier". Only the
# NAMES are pinned here; whether pyproject.toml still declares each one (and
# what it means) is read live by `default_marker_expr()` below, never assumed.
FAST_TIER_GATE_MARKERS = ("cadence", "pending_fix", "designed_red")


def default_marker_expr(pyproject_path: Path = PYPROJECT_PATH) -> str:
    """The fast-tier marker expression, built from markers pyproject.toml
    actually declares today -- never a hardcoded string independent of it.

    Falls back to `DEFAULT_MARKER_EXPR` (the tri-marker expression named in
    this plan chunk's brief) only if pyproject.toml is unreadable or declares
    none of `FAST_TIER_GATE_MARKERS`, so a caller always gets a usable
    expression rather than an empty one.
    """
    try:
        config = load_pytest_config(pyproject_path)
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_MARKER_EXPR
    present = [m for m in FAST_TIER_GATE_MARKERS if m in declared_markers(config)]
    if not present:
        return DEFAULT_MARKER_EXPR
    return " and ".join(f"not {m}" for m in present)


def capped_worker_count(requested: int | None) -> int | None:
    """Clamp `requested` to min(physical_cores // 2, usable_ram_mb // 150).

    None (or <=1) means "run serially, no -n flag at all" -- the safe
    default. NEVER returns an unbounded/auto value.
    """
    if requested is None or requested <= 1:
        return None
    physical_cores = os.cpu_count() or 1
    cap_by_cores = max(1, physical_cores // 2)
    try:
        usable_ram_mb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 * 1024)
    except (ValueError, AttributeError, OSError):
        usable_ram_mb = 8192  # conservative fallback when sysconf is unavailable (Windows)
    cap_by_ram = max(1, int(usable_ram_mb // 150))
    return max(1, min(requested, cap_by_cores, cap_by_ram))


# In-process pytest plugin (pytest/_pytest only -- no third-party report
# plugin dependency; pytest-json-report is not part of this repo's install
# surface). Reads `terminalreporter.stats`, the SAME dict `-q`'s own summary
# line is built from, so this script's counts can never disagree with what a
# human running plain `pytest -q` sees. Written to a temp file and imported
# via `-p <module>` + PYTHONPATH, rather than embedded as a string passed to
# `-p`, because `-p` only accepts an importable module name.
_PLUGIN_SOURCE = '''
import json
import os

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    stats = terminalreporter.stats
    outcomes = ("passed", "failed", "error", "skipped", "xfailed", "xpassed")
    summary = {o: len(stats.get(o, [])) for o in outcomes}
    failed_or_errored = set()
    for o in ("failed", "error"):
        for report in stats.get(o, []):
            nodeid = getattr(report, "nodeid", None)
            if nodeid:
                failed_or_errored.add(nodeid)
    payload = {
        "summary": summary,
        "failed_or_errored": sorted(failed_or_errored),
    }
    out_path = os.environ["RED_SET_REPORT_OUT"]
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
'''

_PLUGIN_MODULE_NAME = "_red_set_report_collector"

# Collection-only plugin (C1b). Hooks `pytest_collection_modifyitems`, which
# fires during collection regardless of `--collect-only` -- so this captures
# the exact node-id set pytest would run, WITHOUT executing a single test.
# Deterministic and outcome-independent: two invocations of this plugin
# (unfiltered, fast-tier-filtered) cannot be perturbed by a peer's concurrent
# edit or a transient failure the way diffing two EXECUTION runs could.
_COLLECT_PLUGIN_SOURCE = '''
import json
import os

import pytest


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(session, config, items):
    # trylast=True: pytest's own -m mark-expression deselection is ALSO a
    # (non-wrapper) pytest_collection_modifyitems hookimpl, registered
    # earlier as a core plugin. Non-wrapper hooks run in LIFO registration
    # order by default, so a plugin loaded later via -p (this one) would
    # otherwise run BEFORE the core deselection -- capturing the nodeid set
    # from before `-m` filtering applied. trylast pins this to run after it.
    nodeids = sorted(item.nodeid for item in items)
    out_path = os.environ["RED_SET_REPORT_COLLECT_OUT"]
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"nodeids": nodeids}, fh)
'''

_COLLECT_PLUGIN_MODULE_NAME = "_red_set_report_collector_collect"


def _child_cwd(target: str) -> Path | None:
    """REPO_ROOT for a relative target or one inside it; inherit the caller's cwd for an
    absolute target in another tree, so that tree's own rootdir/config governs collection."""
    path = Path(target)
    if path.is_absolute() and not path.resolve().is_relative_to(REPO_ROOT):
        return None
    return REPO_ROOT


def run_pytest_collect(
    target: str,
    *,
    marker_expr: str | None = None,
) -> set[str]:
    """Run `pytest --collect-only` against `target`, return the node-id set.

    Executes nothing -- collection is a static property of the tree, so two
    calls of this function (with/without `marker_expr`) cannot be perturbed
    by a peer's concurrent commit landing between them the way two EXECUTION
    runs could (see module docstring, C1b).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = tmp_path / "collect.json"
        plugin_path = tmp_path / f"{_COLLECT_PLUGIN_MODULE_NAME}.py"
        plugin_path.write_text(_COLLECT_PLUGIN_SOURCE, encoding="utf-8", newline="\n")

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            target,
            "-p",
            _COLLECT_PLUGIN_MODULE_NAME,
            "--collect-only",
            "-q",
            "--no-header",
        ]
        if marker_expr:
            cmd += ["-m", marker_expr]

        env = dict(os.environ)
        env["RED_SET_REPORT_COLLECT_OUT"] = str(report_path)
        env[_REENTRANCY_ENV_VAR] = "1"
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(tmp_path) + os.pathsep + existing_pythonpath
            if existing_pythonpath
            else str(tmp_path)
        )

        subprocess.run(
            cmd,
            cwd=_child_cwd(target),
            capture_output=True,
            text=True,
            check=False,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if not report_path.exists():
            raise RuntimeError(
                f"red-set-report collect-only plugin did not write {report_path} "
                f"for target {target!r} -- pytest may have failed to collect"
            )
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        return set(payload.get("nodeids", []))


def current_head_sha() -> str | None:
    """Best-effort `git rev-parse HEAD` -- None if unavailable (e.g. not a
    git checkout), never raises. Used to report whether the tree moved
    across the measurement (C1b's residual-honesty requirement)."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def derive_marked_split(collected_all: set[str], collected_fast: set[str]) -> set[str]:
    """`marked = collected_all - collected_fast`, guarded (C1b).

    Collection is deterministic against a still tree, but a peer landing a
    commit between the two `--collect-only` calls could still violate the
    subset invariant. FAIL LOUDLY (raise, naming node-ids) rather than
    silently proceeding on a corrupt set -- the entire point of this chunk
    is not reintroducing an undetectable tree-moved-under-us failure mode
    one level up.
    """
    offending = sorted(collected_fast - collected_all)
    if offending:
        raise RuntimeError(
            "red-set-report: collected_fast is not a subset of collected_all -- "
            "the tree likely moved between the two --collect-only invocations "
            "(a peer committed mid-measurement). Offending node-id(s): %s" % offending
        )
    return collected_all - collected_fast


def run_pytest_json(
    target: str,
    *,
    marker_expr: str | None,
    workers: int | None,
    extra_args: list[str] | None = None,
) -> dict:
    """Run pytest against `target`, return the parsed collector-plugin payload.

    Uses a temp file for the report (rather than stdout scraping) so pytest's
    own summary noise never has to be parsed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        report_path = tmp_path / "report.json"
        plugin_path = tmp_path / f"{_PLUGIN_MODULE_NAME}.py"
        plugin_path.write_text(_PLUGIN_SOURCE, encoding="utf-8", newline="\n")

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            target,
            "-p",
            _PLUGIN_MODULE_NAME,
            "-q",
            "--no-header",
        ]
        if marker_expr:
            cmd += ["-m", marker_expr]
        capped = capped_worker_count(workers)
        if capped is not None:
            cmd += ["-n", str(capped)]
        if extra_args:
            cmd += extra_args

        env = dict(os.environ)
        env["RED_SET_REPORT_OUT"] = str(report_path)
        env[_REENTRANCY_ENV_VAR] = "1"
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(tmp_path) + os.pathsep + existing_pythonpath
            if existing_pythonpath
            else str(tmp_path)
        )

        subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if not report_path.exists():
            raise RuntimeError(
                f"red-set-report collector plugin did not write {report_path} "
                f"for target {target!r} -- pytest may have failed to start"
            )
        return json.loads(report_path.read_text(encoding="utf-8"))


def _outcome_counts(report: dict) -> dict:
    summary = report.get("summary", {})
    return {
        "total": sum(summary.get(o, 0) for o in ("passed", "failed", "error", "skipped", "xfailed", "xpassed")),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "error": summary.get("error", 0),
        "skipped": summary.get("skipped", 0),
        "xfailed": summary.get("xfailed", 0),
        "xpassed": summary.get("xpassed", 0),
    }


def _failed_or_errored_nodeids(report: dict) -> set[str]:
    return set(report.get("failed_or_errored", []))


def derive_red_set(
    target: str,
    *,
    marker_expr: str | None = None,
    workers: int | None = None,
) -> dict:
    """Derive the marked/unmarked split from COLLECTION, execute ONCE (C1b).

    `marker_expr=None` (the default) resolves live from pyproject.toml via
    `default_marker_expr()` -- never a hardcoded string independent of it.

    Marker membership (`marked` / `unmarked`) is a static property of the
    tree, derived from two `--collect-only` passes (execute nothing, so a
    peer's concurrent edit cannot migrate a cell between the two sets the
    way diffing two EXECUTION runs could). Exactly ONE execution pass
    (unfiltered) supplies the failed/errored set.

    Also captures the git HEAD SHA before and after the whole measurement,
    so a caller can see whether the tree moved rather than trusting it did
    not (C1b's residual-honesty requirement).

    Returns the full JSON-serializable report dict this script emits.
    """
    if marker_expr is None:
        marker_expr = default_marker_expr()

    head_before = current_head_sha()

    collected_all = run_pytest_collect(target, marker_expr=None)
    if not collected_all:
        # Ported from the DoE-plane fork's `derive_observed_red` negative spec
        # (W3-C5, docs/plans/2026-09-18-doe-holds-no-scripts.md): a vacuous
        # target -- a mistyped path, an empty directory -- must fail loudly
        # here, not report a vacuously green (0 collected, 0 failed) census
        # that reads as "no reds" to a caller diffing the unmarked-failed set
        # against a registry.
        raise ValueError(
            f"red-set-report: target {target!r} collected zero tests -- refusing to report "
            "a red set over an empty corpus"
        )
    collected_fast = run_pytest_collect(target, marker_expr=marker_expr)
    marked = derive_marked_split(collected_all, collected_fast)

    unfiltered = run_pytest_json(target, marker_expr=None, workers=workers)

    head_after = current_head_sha()

    unfiltered_counts = _outcome_counts(unfiltered)
    failed_all = _failed_or_errored_nodeids(unfiltered)

    unmarked_failed = sorted(failed_all & collected_fast)
    marked_failed = sorted(failed_all & marked)

    return {
        "target": target,
        "marker_expr": marker_expr,
        "unfiltered": unfiltered_counts,
        "collected_all_count": len(collected_all),
        "collected_fast_count": len(collected_fast),
        "marked_count": len(marked),
        "unmarked_failed_count": len(unmarked_failed),
        "unmarked_failed": unmarked_failed,
        "marked_failed_count": len(marked_failed),
        "marked_failed": marked_failed,
        "head_before": head_before,
        "head_after": head_after,
        "tree_moved_during_measurement": head_before != head_after,
    }


_CHILD_PLUGIN_MODULE_NAME = "_red_set_report_child_plugin"
_CHILD_PLUGIN_SOURCE = """
import json
import os

_OUTPUT_PATH = os.environ["_RED_SET_REPORT_OUTPUT"]
_MODE = os.environ["_RED_SET_REPORT_MODE"]

_collected = set()
_failed = set()


def pytest_itemcollected(item):
    _collected.add(item.nodeid)


def pytest_runtest_logreport(report):
    if _MODE == "observe" and report.failed:
        _failed.add(report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    with open(_OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump({"collected": sorted(_collected), "failed": sorted(_failed)}, fh)
"""


def _repo_root(explicit: Optional[str]) -> Path:
    return Path(explicit).resolve() if explicit else Path.cwd()


def _tier_last_run_path(repo_root: Path) -> Path:
    return repo_root / "coordinator" / "bin" / "tier-last-run.py"


def _load_tier_last_run_module(repo_root: Path):
    """Load `coordinator/bin/tier-last-run.py` by path (hyphenated filename, not import-able).

    Reused for its `_validate_entry` -- the single parser for `coordinator.local.md`'s
    `ceremony_test_cmds`, per this module's own negative spec.
    """
    path = _tier_last_run_path(repo_root)
    spec = importlib.util.spec_from_file_location("_red_set_report_tier_last_run", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_entry(repo_root: Path, entry_name: str) -> dict:
    """The declared `ceremony_test_cmds` entry for `entry_name`, validated by `tier-last-run.py`.

    Raises `ValueError` (never a raw exception) on an unknown entry name or an unresolvable
    `collection_roots` path -- identical validation to `tier-last-run.py record`/`read`.
    """
    module = _load_tier_last_run_module(repo_root)
    return module._validate_entry(repo_root, entry_name)


def guard_not_nested() -> None:
    """Refuse to run when already inside a pytest process, rather than recursing into it.

    `PYTEST_CURRENT_TEST` is set by pytest itself for the duration of every test's execution --
    its presence here means this script is being invoked FROM a running test, not standalone.
    Applied to the execution leg (`derive_observed_red`) and the CLI entrypoint; the
    collection-only leg (`run_pytest_collect`) is exempt -- see this module's negative spec.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError(
            "red-set-report.py refuses to run its execution leg from inside a running pytest "
            "process (PYTEST_CURRENT_TEST is set) -- this would recurse into the suite that "
            "invoked it rather than reporting an observed red set. Invoke it as a standalone "
            "script, or from the skip-by-default execution gate."
        )


def assert_no_self_containment(repo_root: Path, roots: list) -> None:
    """Refuse a `collection_roots` entry that contains this file's own path.

    Carry-over from claude-klabauter's lesson `2026-08-07-a-gate-that-measures-a-corpus-must-not-live-
    inside-it`: a prior version of a ratchet like this one sat inside the directory it measured
    and recursed unboundedly, discovered only because a plain run never returned.
    """
    self_path = Path(__file__).resolve()
    for root in roots:
        root_path = (repo_root / root).resolve()
        if self_path == root_path or self_path.is_relative_to(root_path):
            raise ValueError(
                f"declared collection_root '{root}' contains this gate module ({self_path}) -- "
                "a gate that measures a corpus must not live inside it."
            )


def _run_pytest_child(target: str, mode: str) -> dict:
    """Spawn `python -m pytest <target> [--collect-only] -q -p <plugin>` as a CHILD process.

    `mode` is `"collect"` (no test bodies run) or `"observe"` (full execution). The child's
    environment has `PYTEST_CURRENT_TEST` stripped, so it never inherits a false nested-invocation
    signal from a parent pytest session; its `PYTHONPATH` is extended with a temp directory
    carrying the read-nodeid plugin, which writes `{"collected": [...], "failed": [...]}` to a
    temp JSON file the parent reads back. Returns that parsed dict.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        plugin_path = tmp_path / f"{_CHILD_PLUGIN_MODULE_NAME}.py"
        plugin_path.write_text(_CHILD_PLUGIN_SOURCE, encoding="utf-8", newline="\n")
        output_path = tmp_path / "output.json"

        env = dict(os.environ)
        env.pop("PYTEST_CURRENT_TEST", None)
        env["_RED_SET_REPORT_OUTPUT"] = str(output_path)
        env["_RED_SET_REPORT_MODE"] = mode
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(tmp_path), existing_pythonpath) if part
        )

        lib_dir = str(Path(__file__).resolve().parent / "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from python_interp import resolve_console_python

        args = [
            resolve_console_python() or sys.executable,
            "-m", "pytest", target, "-q", "-p", _CHILD_PLUGIN_MODULE_NAME,
        ]
        if mode == "collect":
            args.append("--collect-only")

        result = subprocess.run(
            args,
            env=env,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if not output_path.exists():
            raise RuntimeError(
                f"pytest child process produced no output for target {target!r} in mode "
                f"{mode!r} (exit {result.returncode}); stderr tail: "
                f"{result.stderr.strip()[-2000:]}"
            )
        return json.loads(output_path.read_text(encoding="utf-8"))


def run_pytest_observe(target: str) -> tuple:
    """Full execution pass over `target`, as a child process.

    Returns `(collected_nodeids, failed_nodeids)`, both sets. This is the ~185s leg -- it runs
    every test body under `target`. Callers gate this behind an explicit opt-in; it must never
    run unconditionally in a fast tier.
    """
    data = _run_pytest_child(target, "observe")
    return set(data.get("collected", [])), set(data.get("failed", []))


def derive_observed_red(repo_root: Path, entry_name: str) -> dict:
    """Run the declared `ceremony_test_cmds` entry `entry_name` and report its observed red set.

    Raises `ValueError` if the entry declares no `collection_roots`, if any root contains this
    module, or if the roots collectively resolve to zero collected tests -- the denominator
    assertion this module's negative spec requires: a vacuous corpus must fail loudly, never
    report an empty (falsely green) red set.

    Deliberately carries no `guard_not_nested()` call of its own -- `coordinator/tests/
    test_known_red_ratchet.py`'s skip-by-default execution gate calls this directly from inside
    a running pytest session, by design (that IS "running it explicitly"). Every pytest
    invocation inside this function is a child process (`_run_pytest_child`), so nothing here
    shares process state with the caller regardless of nesting. `guard_not_nested()` instead
    guards the standalone CLI entrypoint (`main`), which is the path that would otherwise recurse
    an in-process `pytest.main()` call.
    """
    entry = resolve_entry(repo_root, entry_name)
    roots = entry.get("collection_roots") or []
    if not roots:
        raise ValueError(f"ceremony_test_cmds entry '{entry_name}' declares no collection_roots")
    assert_no_self_containment(repo_root, roots)

    collected: set = set()
    failed: set = set()
    for root in roots:
        target = str(repo_root / root)
        root_collected, root_failed = run_pytest_observe(target)
        collected |= root_collected
        failed |= root_failed

    if not collected:
        raise ValueError(
            f"collection_roots for entry '{entry_name}' resolved to zero collected tests -- "
            "refusing to report a red set over an empty corpus"
        )

    return {
        "entry": entry_name,
        "collection_roots": roots,
        "collected_count": len(collected),
        "red_nodeids": sorted(failed),
    }


def derive_known_red_count(repo_root: Path, registry_filename: str) -> dict:
    """The known-red count for a registry, DERIVED as `len(entries)` rather than declared.

    PM ruling 2026-08-28: a known-red count is computed, never hand-maintained. The hand-pinned
    `known_red_count: 29` this replaces was not merely stale -- it counted a different UNIT.
    `python -m pytest` reports one failure event per report, and a parametrized test can emit
    several for one nodeid, so the declared number flapped 29 -> 28 -> 27 across runs while the
    real set held at 25 (`state/bug-backlog/2026-08-25-hook-test-tier-29-reds-are-four-distinct-
    causes.yaml`, RESOLVED 2026-08-27). Two sessions then read `29 - 25` as four unidentified
    reds and proposed acting on a gap that never existed.

    Deriving from the registry makes that arithmetic impossible rather than merely discouraged:
    the count becomes a projection of the nodeid set, so it cannot disagree with it and cannot
    silently become an event count again.

    Zero-spawn -- reads the registry, never executes the tier. `derive_observed_red` above is the
    one that runs pytest; these answer different questions and only that one costs a tier run.

    `seeded_from` is reported VERBATIM rather than reduced to a boolean. A registry can hold rows
    without ever having been seeded -- a deliberately enrolled entry (`fast-full` took one at
    `20132f1a3` while still carrying `seeded_from: null`) is a real row from a known cause, not a
    partial seeding run. A `seeded: false` field printed beside a non-zero count would be the same
    two-numbers-one-property trap this function exists to close, one level up.

    Note what does NOT need this number: shrink-only. The ratchet enforces shrink-only on the SET
    (`offenders_not_in_registry` -- an observed red with no entry fails), which is strictly
    stronger than a monotone count and catches a fix-one-break-one swap that leaves any count flat.
    """
    registry_path = repo_root / "state" / registry_filename
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = registry.get("entries", {})
    return {
        "registry": registry_filename,
        "registry_for": registry.get("registry_for"),
        "known_red_count": len(entries),
        "seeded_from": registry.get("seeded_from"),
        "unit": "unique nodeids (never failure-report events)",
    }


def cmd_count(args: argparse.Namespace) -> int:
    repo_root = _repo_root(args.repo_root)
    try:
        result = derive_known_red_count(repo_root, args.registry)
    except (OSError, ValueError) as exc:
        print(f"red-set-report count: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_observed(args: argparse.Namespace) -> int:
    repo_root = _repo_root(args.repo_root)
    try:
        result = derive_observed_red(repo_root, args.entry)
    except (ValueError, RuntimeError) as exc:
        print(f"red-set-report observed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def human_summary_line(report: dict) -> str:
    u = report["unfiltered"]
    return (
        f"[red-set-report] {report['target']}: "
        f"{u['total']} collected, {u['passed']} passed, {u['failed']} failed, "
        f"{u['error']} errored, {u['skipped']} skipped, {u['xfailed']} xfailed -- "
        f"{report['unmarked_failed_count']} failed/errored with NO cadence/pending_fix/"
        f"designed_red marker"
    )


def build_doe_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="red-set-report.py",
        description=(
            "Derive the observed red-nodeid SET for a declared ceremony_test_cmds entry, via a "
            "child-process pytest plugin reading report.nodeid -- never stdout scraping."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="repo root to resolve coordinator.local.md against (default: cwd)",
    )
    subparsers = parser.add_subparsers(dest="verb", required=True)

    observed = subparsers.add_parser(
        "observed", help="run the entry's declared collection_roots and emit the observed red set"
    )
    observed.add_argument("--entry", required=True, help="ceremony_test_cmds entry name")
    observed.set_defaults(func=cmd_observed)

    count = subparsers.add_parser(
        "count",
        help=(
            "derive the known-red count from a registry (len of its nodeid set) -- zero-spawn, "
            "reads the registry and never runs the tier"
        ),
    )
    count.add_argument(
        "--registry",
        required=True,
        help="registry filename under state/ (e.g. hook-tier-known-red.json)",
    )
    count.set_defaults(func=cmd_count)

    return parser


_DOE_VERBS = ("observed", "count")


def _is_doe_invocation(argv: list[str]) -> bool:
    """True when argv is `[--repo-root R] observed|count ...` -- the DoE verb shape."""
    rest = list(argv)
    if rest and rest[0] == "--repo-root":
        rest = rest[2:]
    elif rest and rest[0].startswith("--repo-root="):
        rest = rest[1:]
    return bool(rest) and rest[0] in _DOE_VERBS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="red-set-report.py",
        description="Derive (never assert) the red-cell census for a pytest path.",
    )
    p.add_argument("target", help="pytest target path, e.g. coordinator_core/bash_guards/tests/")
    p.add_argument(
        "--marker-expr",
        default=None,
        help="fast-tier marker expression (default: derived live from "
        "pyproject.toml's declared cadence/pending_fix/designed_red markers)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help="capped worker count (default: serial, no -n flag). NEVER bare -n auto.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if _is_doe_invocation(argv):
        guard_not_nested()
        args = build_doe_parser().parse_args(argv)
        return args.func(args)
    if os.environ.get(_REENTRANCY_ENV_VAR):
        print(
            "[red-set-report] FATAL: nested red-set-report.py invocation detected "
            "(%s already set in the environment). This means the target tree "
            "contains a test cell that itself shells out to red-set-report.py "
            "with no marker filter -- that recurses without bound. Move the "
            "offending test out of the measured tree; do not silently no-op "
            "here, a vacuous pass would be worse than the recursion." % _REENTRANCY_ENV_VAR,
            file=sys.stderr,
        )
        return 1
    args = build_parser().parse_args(argv)
    report = derive_red_set(args.target, marker_expr=args.marker_expr, workers=args.workers)
    print(json.dumps(report, indent=2))
    print(human_summary_line(report), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
