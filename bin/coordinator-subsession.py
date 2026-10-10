"""coordinator/bin/coordinator-subsession.py -- a refusing launcher for a
`claude -p` subsession.

Usage:

    coordinator-subsession.py [--cwd DIR] [--plugin-dir P]
        [--fidelity-report PATH] [--require-fidelity] -- <claude -p args...>

Everything after the first bare `--` is the passthrough argv handed to the
`claude` binary unaltered; everything before it is this launcher's own flags.

WHY THIS EXISTS. A `claude -p` subsession spawned with no working guard plane
and no reachable engine runs coordinator-blind: every guard, hook, and op the
parent session relies on silently no-ops, and nothing about the child's
output says so (`docs/plans/2026-09-26-coordinator-subsession-fidelity.md`).
This launcher performs a zero-spawn PREFLIGHT before it will spawn `claude`
at all, and refuses (exit 3, no child) rather than hand back a session whose
fidelity it could not establish. `--require-fidelity` without
`--fidelity-report` is a usage error (exit 2) checked before preflight, not a
preflight failure -- E1.o1: the fidelity report has exactly one channel, an
explicit path.

This module resolves its own root from `__file__`, never from cwd -- it can
be invoked from anywhere. Preflight itself performs ZERO subprocess spawns:
it composes `_hook_plane_probe.hook_plane_verdict` (a stdlib-only static
resolvability probe, C2) with an in-process `_engine_root.resolve_claude_klabauter_root`
call. The second condition mirrors `experiments/naked-vs-coordinator/
arms.py::_require_engine`'s check WITHOUT that function's `python3` subprocess
round trip -- same predicate (the resolved root contains `coordinator_core`),
paid for as an import instead of a spawn.

C6 (this chunk) adds the session-end leg: when `--fidelity-report PATH` is
given, a pre-spawn snapshot of the target's git state and its `docs/plans/`
and sizing-object directory listings is taken before the child runs, and a
JSON report is written to PATH (atomic replace) after the child exits --
never to stderr, which the child inherits and cannot be trusted not to
interleave with. With no `--fidelity-report`, no snapshot is taken and
nothing is written: fidelity was not asked for. `--require-fidelity` turns a
sizing/prep-gate miss into exit 4 when the child itself exited 0.

The sizing-object directory is resolved by importing
`coordinator-doc-new.py`'s own `_default_output_path` type-to-directory
logic (the resolved engine root's `coordinator/bin/coordinator-doc-new.py`)
rather than shelling out or hardcoding `state/sizings/`. When that is not
importable from here, the `sizing_fired` field is recorded as the string
`"unresolved"` rather than a guessed path or a silently-false verdict. Each
new-or-modified plan's `prep_gate` verdict reuses `mise-prep-gate.py::
prep_gate` -- the same PREPPED/NOT-PREPPED/REFUSED/ENGINE-ERROR verdict set
`emit-dispatch-workflow.py`'s in-session bar already reads -- so the two legs
cannot diverge on what "passing" means.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


class _PreflightFailure(Exception):
    """One failed preflight condition: `condition` names which check failed,
    `reason` is the human-readable detail for the `refused: <condition>:
    <reason>` stderr line."""

    def __init__(self, condition: str, reason: str) -> None:
        super().__init__(f"{condition}: {reason}")
        self.condition = condition
        self.reason = reason


def _hooks_scripts_dir() -> Path:
    return _REPO_ROOT / "coordinator" / "hooks" / "scripts"


def _load_hook_plane_probe():
    hooks_scripts_dir = _hooks_scripts_dir()
    if str(hooks_scripts_dir) not in sys.path:
        sys.path.insert(0, str(hooks_scripts_dir))
    import _hook_plane_probe  # type: ignore

    return _hook_plane_probe


def _load_engine_root():
    hooks_scripts_dir = _hooks_scripts_dir()
    if str(hooks_scripts_dir) not in sys.path:
        sys.path.insert(0, str(hooks_scripts_dir))
    import _engine_root  # type: ignore

    return _engine_root


def _check_guard_plane(config_dir: Path, project_dir: Path, plugin_dir: "Path | None") -> None:
    """Condition (1): `hook_plane_verdict` must report `armed`. Raises
    `_PreflightFailure` on any non-armed verdict, zero spawns."""
    probe = _load_hook_plane_probe()
    verdict = probe.hook_plane_verdict(config_dir, project_dir, plugin_dir)
    if not verdict.get("armed"):
        reason = verdict.get("reason") or ""
        missing = verdict.get("missing_files") or []
        if missing:
            reason = f"{reason} (missing: {', '.join(missing)})" if reason else (
                f"missing: {', '.join(missing)}"
            )
        raise _PreflightFailure("guard-plane-unarmed", reason or "hook plane not armed")


def _check_engine(env: dict) -> None:
    """Condition (2): the engine root must resolve and contain
    `coordinator_core`. Mirrors `arms.py::_require_engine`'s predicate without
    its `python3` subprocess -- an in-process import instead of a spawn."""
    engine_root_mod = _load_engine_root()
    root = engine_root_mod.resolve_claude_klabauter_root()
    if not root or not (Path(root) / "coordinator_core").is_dir():
        raise _PreflightFailure(
            "engine-unresolvable", f"engine root did not resolve to a coordinator_core checkout: {root!r}"
        )


def _load_mise_prep_gate():
    """Load `mise-prep-gate.py` by file path -- same
    `importlib.util.spec_from_file_location` idiom
    `emit-dispatch-workflow.py::_load_mise_prep_gate` uses for the same
    hyphenated sibling. Monkeypatchable in tests, like `_load_engine_root`."""
    gate_path = _load_engine_root().resolve_engine_bin_script("mise-prep-gate.py")
    assert gate_path is not None, "engine copy of mise-prep-gate.py unresolved"
    spec = importlib.util.spec_from_file_location(
        "_coordinator_subsession_mise_prep_gate", gate_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_coordinator_doc_new(engine_root: Path):
    """Load `coordinator-doc-new.py` by file path from the resolved engine
    root. Raises on any failure -- the caller records the sizing directory
    as unresolved rather than guessing one."""
    path = Path(engine_root) / "coordinator" / "bin" / "coordinator-doc-new.py"
    if not path.is_file():
        raise FileNotFoundError(str(path))
    spec = importlib.util.spec_from_file_location(
        "_coordinator_subsession_coordinator_doc_new", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_sizing_dir(engine_root: "Path | None", repo_root: Path) -> "Path | None":
    """Resolve the sizing-object directory by importing coordinator-doc-new's
    own type-to-directory logic for `sizing-object`, never by shelling out or
    hardcoding `state/sizings/`. Returns `None` (unresolved) on any failure."""
    if engine_root is None:
        return None
    try:
        module = _load_coordinator_doc_new(engine_root)
        rel = module._default_output_path(
            "sizing-object", "coordinator-subsession-fidelity-probe", None
        )
    except Exception:
        return None
    return repo_root / Path(rel).parent


def _listing_snapshot(dir_path: "Path | None") -> dict:
    """name -> mtime_ns for every file directly under `dir_path`. Empty when
    the directory does not exist (or is unresolved)."""
    if dir_path is None or not dir_path.is_dir():
        return {}
    snap = {}
    for entry in dir_path.iterdir():
        if entry.is_file():
            try:
                snap[entry.name] = entry.stat().st_mtime_ns
            except OSError:
                continue
    return snap


def _new_names(before: dict, after: dict) -> list:
    return sorted(set(after) - set(before))


def _new_or_modified_names(before: dict, after: dict) -> list:
    return sorted(name for name, mtime in after.items() if before.get(name) != mtime)


def _git_snapshot(repo_root: Path) -> "dict | None":
    """`None` means "no git repo here" (or git itself is unusable) -- the
    caller reports `diff_bearing: null` for that case rather than guessing a
    dirty/clean answer."""
    _no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        head = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            creationflags=_no_window,
        )
    except Exception:
        return None
    if head.returncode != 0:
        return None
    try:
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
            creationflags=_no_window,
        )
    except Exception:
        return None
    if status.returncode != 0:
        return None
    return {"head": head.stdout.strip(), "porcelain": status.stdout}


class _FidelitySnapshot:
    """Pre-spawn artifact state -- taken only when `--fidelity-report` was
    given, and only once, before the child is spawned."""

    def __init__(self, repo_root: Path, engine_root: "Path | None") -> None:
        self.repo_root = repo_root
        self.git_before = _git_snapshot(repo_root)
        self.plans_dir = repo_root / "docs" / "plans"
        self.plans_before = _listing_snapshot(self.plans_dir)
        self.sizing_dir = _resolve_sizing_dir(engine_root, repo_root)
        self.sizing_before = _listing_snapshot(self.sizing_dir)


def _plan_brief_entry(gate, plan_path: Path) -> "tuple[str, bool] | None":
    """`(rel_path, note_non_empty)` for a plan carrying
    `execution_authorized_by`, else `None`. Reported, not enforced -- pm-brief
    owns enforcement."""
    try:
        text = plan_path.read_text(encoding="utf-8", errors="replace")
        fm, err = gate._frontmatter(text)
    except Exception:
        return None
    if err or not fm or "execution_authorized_by" not in fm:
        return None
    note = fm.get("execution_authorized_note")
    return bool(note and str(note).strip())


def _build_fidelity_report(snapshot: "_FidelitySnapshot") -> dict:
    """The whole post-run fidelity report. Never raises for a single
    unresolvable sub-field -- each such field is recorded as unresolved
    rather than aborting the whole report."""
    repo_root = snapshot.repo_root

    if snapshot.sizing_dir is None:
        sizing_fired: "bool | str" = "unresolved"
    else:
        sizing_after = _listing_snapshot(snapshot.sizing_dir)
        sizing_fired = bool(_new_names(snapshot.sizing_before, sizing_after))

    plans_after = _listing_snapshot(snapshot.plans_dir)
    changed_names = _new_or_modified_names(snapshot.plans_before, plans_after)

    try:
        gate = _load_mise_prep_gate()
        corpus = gate.corpus_inputs(repo_root)
    except Exception:
        gate = None
        corpus = None

    plans_report = []
    brief_report = {}
    for name in changed_names:
        plan_path = snapshot.plans_dir / name
        rel = (Path("docs") / "plans" / name).as_posix()
        verdict = None
        if gate is not None:
            try:
                verdict = gate.prep_gate(plan_path, corpus)["verdict"]
            except Exception:
                verdict = gate.ENGINE_ERROR
        plans_report.append({"path": rel, "prep_gate": verdict})
        if gate is not None:
            entry = _plan_brief_entry(gate, plan_path)
            if entry is not None:
                brief_report[rel] = entry

    git_after = _git_snapshot(repo_root)
    diff_bearing = None if snapshot.git_before is None else (git_after != snapshot.git_before)

    return {
        "sizing_fired": sizing_fired,
        "plans": plans_report,
        "brief": brief_report,
        "diff_bearing": diff_bearing,
        "terminal_gate": "pending-R8",
    }


def _fidelity_failed(report: dict) -> bool:
    """`--require-fidelity`'s own bar: sizing did not fire, or any plan
    failed the mise-prep bar (a non-PREPPED verdict, including
    "unresolved" gate/sizing states)."""
    if report["sizing_fired"] is not True:
        return True
    return any(p["prep_gate"] != "PREPPED" for p in report["plans"])


def _write_fidelity_report(path: Path, report: dict) -> None:
    """Atomic replace: a temp file in the same directory, then `os.replace`,
    so a reader never observes a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".fidelity-report-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_name, str(path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _split_argv(argv: list) -> "tuple[list, list]":
    """Split `argv` at the first bare `--`: everything before is this
    launcher's own flags, everything after is the passthrough argv handed to
    `claude` unaltered. No `--` present means no passthrough args."""
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1 :]
    return argv, []


def _parse_own_flags(flags: list) -> dict:
    parsed = {
        "cwd": None,
        "plugin_dir": None,
        "fidelity_report": None,
        "require_fidelity": False,
    }
    i = 0
    while i < len(flags):
        flag = flags[i]
        if flag == "--cwd":
            i += 1
            parsed["cwd"] = flags[i]
        elif flag == "--plugin-dir":
            i += 1
            parsed["plugin_dir"] = flags[i]
        elif flag == "--fidelity-report":
            i += 1
            parsed["fidelity_report"] = flags[i]
        elif flag == "--require-fidelity":
            parsed["require_fidelity"] = True
        else:
            raise SystemExit(f"refused: unrecognized-flag: {flag}")
        i += 1
    return parsed


def main(argv: "list | None" = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    own_flags, passthrough = _split_argv(raw_argv)
    if "-h" in own_flags or "--help" in own_flags:
        print(__doc__)
        return 0
    opts = _parse_own_flags(own_flags)

    if opts["require_fidelity"] and not opts["fidelity_report"]:
        print(
            "refused: usage: --require-fidelity requires --fidelity-report PATH",
            file=sys.stderr,
        )
        return 2

    cwd = Path(opts["cwd"]) if opts["cwd"] else Path.cwd()
    plugin_dir = Path(opts["plugin_dir"]) if opts["plugin_dir"] else None
    config_dir = Path(os.environ["CLAUDE_CONFIG_DIR"]) if os.environ.get("CLAUDE_CONFIG_DIR") else (
        Path.home() / ".claude"
    )

    failures: list = []
    try:
        _check_guard_plane(config_dir, cwd, plugin_dir)
    except _PreflightFailure as exc:
        failures.append(exc)

    child_env = dict(os.environ)
    try:
        _check_engine(child_env)
    except _PreflightFailure as exc:
        failures.append(exc)

    if failures:
        for failure in failures:
            print(f"refused: {failure.condition}: {failure.reason}", file=sys.stderr)
        return 3

    child_env["COORDINATOR_SUBSESSION_FIDELITY"] = "1"

    claude_bin = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not claude_bin:
        print("refused: claude-binary-unresolvable: CLAUDE_BIN unset and 'claude' not on PATH", file=sys.stderr)
        return 3

    cmd = [claude_bin]
    if plugin_dir is not None:
        cmd += ["--plugin-dir", str(plugin_dir)]
    cmd += list(passthrough)

    fidelity_report_path = Path(opts["fidelity_report"]) if opts["fidelity_report"] else None
    snapshot = None
    if fidelity_report_path is not None:
        try:
            engine_root_val = _load_engine_root().resolve_claude_klabauter_root()
        except Exception:
            engine_root_val = None
        snapshot = _FidelitySnapshot(
            cwd, Path(engine_root_val) if engine_root_val else None
        )

    # No stdin/stdout/stderr redirection: the default (None) inherits the
    # parent's file descriptors directly, so a caller parsing
    # `--output-format json` off this launcher's stdout sees the child's
    # stdout byte-for-byte, unbuffered by this process.
    result = subprocess.run(cmd, env=child_env)

    if snapshot is not None:
        report = _build_fidelity_report(snapshot)
        _write_fidelity_report(fidelity_report_path, report)
        if opts["require_fidelity"] and result.returncode == 0 and _fidelity_failed(report):
            return 4

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
