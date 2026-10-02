"""land-goals — land the goal-blitz drafts that carry a recorded the VP-Product Reviewer ratification, and nothing else.

A goal-blitz fire drafts, critiques and integrates OKRs in its trail and ratifies nothing. This
module is the only place a draft becomes a goal: goal-setting Steps 4, 5 and 7, run mechanically
through goal-setting's own CLIs (`coordinator-doc-new`, `emit-goal-from-artifact`, the scoped
commit op) for each ratified draft. A draft is never written under `state/goals/` any other way.

Inputs: the workflow's result (the raw object, or the harness task-output envelope wrapping it),
`<trailDir>/<seed-id>.goal-draft.yaml` for every ready seed, and `<trailDir>/ratification.json`
(`{seed_id: {verdict: ratified|declined, ratifier: vp-product, utterance}}`), shaped per
`goal-blitz-contract.json`.

REFUSALS, all before the first write (exit 2, nothing on disk touched):

  - a ready seed with no ratification record, a malformed record, or a `ratifier` other than
    `vp-product` (the VP-Product Reviewer, the VP Product agent, ratifies; no other path ships);
  - a ratified seed whose draft is missing or fails shape (objective, 1-5 key results,
    `period` enum, `period_value`);
  - a result that is neither a goal-blitz result nor an envelope wrapping one.

A `declined` record is honoured: the seed lands nothing and is reported. A ratification for a
seed the readiness gate did not mark ready is ignored and reported, never landed.

A consumed `kind: goal-seed` baton is stamped `deployment_state: shipped` with the sanctioned
`substantively-shipped-no-commit:<date>` token, because the landing commit cannot cite its own
SHA. Seeds of `kind: sizing` carry no baton and are left alone.

Usage:

    python3 land-goals.py --repo-root <abs> --trail-dir <abs> [--no-commit]
                          [--engine-root <abs>] [--doc-new-cli <abs>] <goal-blitz-result.json>

Exit 0 when at least one goal landed, 1 when nothing was ratified (nothing written), 2 on a
refusal, 3 when a CLI failed mid-landing (the paths already written are listed, nothing is
committed).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_NOTHING_RATIFIED = 1
EXIT_REFUSED = 2
EXIT_PARTIAL = 3

PERIODS = ("day", "week", "repo", "quarter", "year")
MAX_KEY_RESULTS = 5
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Refusal(ValueError):
    """A precondition failed before anything was written."""


class CliFailure(RuntimeError):
    """A resolved coordinator CLI exited non-zero."""


def _goal_blitz_result(path: Path) -> dict:
    """The workflow's returned object, from the raw file or the task-output envelope."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "ready" not in data and isinstance(data.get("result"), dict):
        data = data["result"]
    if not isinstance(data, dict) or not isinstance(data.get("ready"), list):
        raise Refusal(
            f"{path}: carries no `ready` list, so it is neither a goal-blitz result nor a "
            "task-output envelope wrapping one."
        )
    return data


def _load_ratification(trail: Path) -> dict:
    path = trail / "ratification.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Refusal(f"{path}: not a JSON object keyed by seed id.")
    return data


def _check_record(seed_id: str, record) -> str:
    """The record's verdict, or a Refusal naming what is wrong with it."""
    if not isinstance(record, dict):
        raise Refusal(f"{seed_id}: ratification record is not an object.")
    if record.get("verdict") not in ("ratified", "declined"):
        raise Refusal(f"{seed_id}: ratification verdict {record.get('verdict')!r} is not ratified|declined.")
    if record.get("ratifier") != "vp-product":
        raise Refusal(
            f"{seed_id}: ratifier {record.get('ratifier')!r} is not `vp-product`. The VP-Product Reviewer sets and "
            "ratifies every OKR, and no other ratification path ships."
        )
    if record["verdict"] == "ratified" and not str(record.get("utterance") or "").strip():
        raise Refusal(f"{seed_id}: a ratified record carries no utterance.")
    return record["verdict"]


def _slug(seed_id: str) -> str:
    """Mirror of goal-blitz.mjs `slug`: the workflow names each draft file by this, not the raw id."""
    return re.sub(r"[^a-z0-9]+", "-", seed_id.lower()).strip("-")


def _load_draft(trail: Path, seed_id: str) -> dict:
    """The seed's integrated draft, shape-checked. Needs PyYAML (the repo's own YAML reader)."""
    if not re.fullmatch(r"[\w.-]+", seed_id):
        raise Refusal(f"{seed_id!r} is not a safe seed id.")
    path = trail / f"{_slug(seed_id)}.goal-draft.yaml"
    if not path.is_file():
        raise Refusal(f"{seed_id}: ratified, but there is no draft at {path}.")
    try:
        import yaml
    except ImportError as exc:
        raise Refusal("PyYAML is required to read goal drafts.") from exc
    draft = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(draft, dict):
        raise Refusal(f"{path}: not a YAML mapping.")
    if not str(draft.get("objective") or "").strip():
        raise Refusal(f"{path}: empty objective.")
    krs = draft.get("key_results")
    if not isinstance(krs, list) or not 1 <= len(krs) <= MAX_KEY_RESULTS:
        raise Refusal(f"{path}: key_results must be a list of 1-{MAX_KEY_RESULTS}.")
    for kr in krs:
        text = kr.get("text") if isinstance(kr, dict) else kr
        if not isinstance(text, str) or not text.strip():
            raise Refusal(f"{path}: a key result has no text.")
    if draft.get("period") not in PERIODS:
        raise Refusal(f"{path}: period {draft.get('period')!r} is not one of {'|'.join(PERIODS)}.")
    if not str(draft.get("period_value") or "").strip():
        raise Refusal(f"{path}: empty period_value.")
    for key in ("roadmap_seeds", "goal_seeds"):
        items = draft.get(key) or []
        if not isinstance(items, list) or not all(isinstance(i, str) and i.strip() for i in items):
            raise Refusal(f"{path}: {key} must be a list of non-empty strings.")
    return draft


def _seed_index(trail: Path) -> dict[str, dict]:
    """Seed id -> candidate row, from the emitter's `candidates.json`; empty when absent."""
    path = trail / "candidates.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("seeds") or []
    return {row["id"]: row for row in data if isinstance(row, dict) and row.get("id")}


def plan_landing(result: dict, ratification: dict, trail: Path) -> tuple[list[tuple[str, dict]], list[str]]:
    """Decide what lands, or raise Refusal. Pure over its inputs plus the draft files; writes nothing.

    Returns the (seed_id, draft) pairs to land, in `ready` order, and report lines for the rest.
    """
    notes: list[str] = []
    to_land: list[tuple[str, dict]] = []
    ready = [s for s in result["ready"] if isinstance(s, str)]
    for seed_id in ready:
        if seed_id not in ratification:
            raise Refusal(
                f"{seed_id}: ready, but {trail / 'ratification.json'} records no ratification for "
                "it. A draft is not a goal until the VP-Product Reviewer has ratified it."
            )
        if _check_record(seed_id, ratification[seed_id]) == "declined":
            notes.append(f"declined by the VP-Product Reviewer, nothing landed: {seed_id}")
            continue
        to_land.append((seed_id, _load_draft(trail, seed_id)))
    for seed_id in ratification:
        if seed_id not in ready:
            notes.append(f"ratification for {seed_id} ignored: the readiness gate did not mark it ready")
    return to_land, notes


def _settings_bin() -> Path:
    home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(
        Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"
    )
    return Path(home) / "bin"


def _launcher(name: str, engine_root: Path | None = None) -> list[str]:
    """argv prefix for a coordinator CLI: the settings-home launcher, else the engine's script."""
    bin_dir = _settings_bin()
    for candidate in (f"{name}.exe", name):
        if (bin_dir / candidate).is_file():
            return [str(bin_dir / candidate)]
    if engine_root is not None:
        script = engine_root / "coordinator" / "bin" / f"{name}.py"
        if script.is_file():
            return [sys.executable, str(script)]
    raise Refusal(
        f"no `{name}` launcher under {bin_dir}, and no --engine-root script to fall back to."
    )


def _run(argv: list[str], cwd: Path) -> str:
    """Run a resolved CLI by argv list and return stdout. The seam tests replace."""
    proc = subprocess.run(
        argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        timeout=600, creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise CliFailure(f"{Path(argv[0]).name} exited {proc.returncode}: "
                         f"{(proc.stderr or proc.stdout).strip()[:800]}")
    return proc.stdout


def _printed_path(stdout: str, repo_root: Path) -> Path:
    """The scaffold path a doc-new run printed (last non-empty stdout line), repo-relative."""
    lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
    if not lines:
        raise CliFailure("coordinator-doc-new printed no path.")
    path = Path(lines[-1])
    return path.resolve().relative_to(repo_root) if path.is_absolute() else path


def _title(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0]


def _yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _fill_goal(scaffold: str, draft: dict) -> str:
    """Write the draft into the scaffolded goal artifact, keeping the scaffold's comments."""
    blocks = []
    for n, kr in enumerate(draft["key_results"], 1):
        text, kind = (kr["text"], kr.get("kind")) if isinstance(kr, dict) else (kr, None)
        blocks.append(
            f"  - id: kr-{n}\n    text: {_yaml_str(text.strip())}\n"
            f"    kind: {kind if kind in ('output', 'outcome') else 'outcome'}\n"
            "    status: not-started\n    weekly_perceptible: true\n    evidence_source: null\n"
        )
    edits = (
        (r"^objective:.*$", f"objective: {_yaml_str(draft['objective'].strip())}"),
        (r"^key_results:\n(?:[ \t].*\n?)+", "key_results:\n" + "".join(blocks)),
        (r"^period:.*$", f"period: {draft['period']}"),
        (r"^period_value:.*$", f"period_value: {_yaml_str(str(draft['period_value']).strip())}"),
        (r"^status:.*$", "status: active"),
    )
    for pattern, replacement in edits:
        scaffold, n = re.subn(pattern, lambda _m, r=replacement: r, scaffold, count=1, flags=re.M)
        if n != 1:
            raise CliFailure(f"the goal scaffold no longer matches /{pattern}/; update land-goals.py.")
    return scaffold


def _goal_id(text: str) -> str:
    match = re.search(r'^id:\s*"?([^"\n]+?)"?\s*$', text, re.M)
    if not match:
        raise CliFailure("the goal scaffold carries no `id:`.")
    return match.group(1)


def _fill_goal_seed(scaffold: str, slice_text: str) -> str:
    """Capture the deferred vision-slice verbatim under `## What this covers`."""
    return re.sub(r"<!-- Capture the deferred.*?-->", lambda _m: slice_text.strip(), scaffold,
                  count=1, flags=re.S)


def _stamp_consumed_baton(text: str, today: str) -> str | None:
    """The baton text marked shipped, or None when it is not an awaiting/ready goal-seed."""
    if not re.search(r"^kind:\s*goal-seed\s*$", text, re.M):
        return None
    new, n = re.subn(
        r"^deployment_state:\s*(?:awaiting_gate|ready_to_fire)\s*$",
        f"deployment_state: shipped\nshipped_in: \"substantively-shipped-no-commit:{today}\"\n"
        "shipped_in_kind: no-commit",
        text, count=1, flags=re.M,
    )
    return new if n else None


def _dirty(repo_root: Path) -> set[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=str(repo_root),
        capture_output=True, text=True, encoding="utf-8", creationflags=_NO_WINDOW,
    ).stdout
    return {ln[3:].split(" -> ")[-1].strip().strip('"') for ln in out.splitlines() if ln[3:].strip()}


def land_one(repo_root: Path, seed_id: str, draft: dict, seed_row: dict | None, clis: dict,
             written: list[str], run=_run) -> str:
    """Land one ratified draft; every path created or edited is appended to `written` at once."""
    out = run(clis["doc_new"] + ["--type", "goal", "--title", _title(draft["objective"])], repo_root)
    goal_rel = _printed_path(out, repo_root)
    written.append(goal_rel.as_posix())
    goal_path = repo_root / goal_rel
    scaffold = goal_path.read_text(encoding="utf-8")
    goal_path.write_text(_fill_goal(scaffold, draft), encoding="utf-8", newline="\n")
    goal_id = _goal_id(scaffold)
    run(clis["emit_goal"] + ["--root", str(repo_root), str(goal_path)], repo_root)

    for title in draft.get("roadmap_seeds") or []:
        out = run(clis["doc_new"] + ["--type", "roadmap-seed", "--goals", goal_id,
                                     "--title", title.strip(), "--summary", _title(title, 140)], repo_root)
        written.append(_printed_path(out, repo_root).as_posix())
    for slice_text in draft.get("goal_seeds") or []:
        out = run(clis["doc_new"] + ["--type", "goal-seed", "--title", _title(slice_text),
                                     "--summary", _title(slice_text, 140)], repo_root)
        rel = _printed_path(out, repo_root)
        written.append(rel.as_posix())
        stub = repo_root / rel
        stub.write_text(_fill_goal_seed(stub.read_text(encoding="utf-8"), slice_text),
                        encoding="utf-8", newline="\n")

    if seed_row and seed_row.get("kind") == "goal-seed" and seed_row.get("path"):
        baton = repo_root / seed_row["path"]
        if baton.is_file():
            stamped = _stamp_consumed_baton(baton.read_text(encoding="utf-8"),
                                            datetime.date.today().isoformat())
            if stamped is not None:
                baton.write_text(stamped, encoding="utf-8", newline="\n")
                written.append(Path(seed_row["path"]).as_posix())
    return goal_id


def _commit(repo_root: Path, engine_root: Path | None, paths: list[str], message: str) -> None:
    argv = _launcher("coordinator-invoke", engine_root) + [
        "ceremony.commit_v2", json.dumps({"paths": paths, "message": message})]
    _run(argv, repo_root)


def main(argv=None, run=_run) -> int:
    ap = argparse.ArgumentParser(prog="land-goals", description=__doc__.split("\n", 1)[0])
    ap.add_argument("result", help="goal-blitz result JSON (raw or task-output envelope)")
    ap.add_argument("--repo-root", required=True, help="ABSOLUTE repo root")
    ap.add_argument("--trail-dir", required=True, help="ABSOLUTE trail dir holding the drafts and ratification.json")
    ap.add_argument("--engine-root", help="engine checkout (default: $COORDINATOR_ENGINE_ROOT)")
    ap.add_argument("--doc-new-cli", help="ABSOLUTE coordinator-doc-new path (the fire's provisionSidecarCli)")
    ap.add_argument("--no-commit", action="store_true", help="list the written paths instead of committing")
    args = ap.parse_args(argv)

    def refuse(msg: str) -> int:
        print(f"land-goals: REFUSED — {msg}", file=sys.stderr)
        return EXIT_REFUSED

    repo_root, trail = Path(args.repo_root), Path(args.trail_dir)
    if not repo_root.is_absolute() or not trail.is_absolute():
        return refuse("--repo-root and --trail-dir must be absolute.")
    repo_root = repo_root.resolve()
    er = args.engine_root or os.environ.get("COORDINATOR_ENGINE_ROOT") or ""
    engine_root = Path(er).resolve() if er.strip() else None
    result_path = Path(args.result)
    if not result_path.is_absolute():
        result_path = repo_root / result_path

    try:
        result = _goal_blitz_result(result_path)
        to_land, notes = plan_landing(result, _load_ratification(trail), trail)
        clis = {
            "doc_new": [args.doc_new_cli] if args.doc_new_cli else _launcher("coordinator-doc-new", engine_root),
            "emit_goal": _launcher("emit-goal-from-artifact", engine_root),
        }
        if to_land and not args.no_commit:
            _launcher("coordinator-invoke", engine_root)
    except (Refusal, OSError, ValueError) as exc:
        return refuse(str(exc))

    for line in notes:
        print(f"land-goals: {line}")
    if not to_land:
        print("land-goals: nothing ratified; nothing written.")
        return EXIT_NOTHING_RATIFIED

    seeds = _seed_index(trail)
    before = _dirty(repo_root)
    written: list[str] = []
    landed: list[str] = []
    try:
        for seed_id, draft in to_land:
            landed.append(land_one(repo_root, seed_id, draft, seeds.get(seed_id), clis, written, run))
            print(f"land-goals: landed {landed[-1]} from {seed_id}")
    except (CliFailure, OSError) as exc:
        print(f"land-goals: FAILED mid-landing — {exc}", file=sys.stderr)
        print("land-goals: written so far (nothing committed):", file=sys.stderr)
        for path in written:
            print(f"    {path}", file=sys.stderr)
        return EXIT_PARTIAL

    paths = sorted(set(written))
    strays = sorted(_dirty(repo_root) - before - set(paths))
    for path in strays:
        print(f"land-goals: NOT committed, appeared during the landing and was not named by a CLI: {path}",
              file=sys.stderr)

    stubs = len(paths) - len(landed)
    if args.no_commit:
        print("land-goals: --no-commit; paths this landing wrote:")
        for path in paths:
            print(f"    {path}")
        return EXIT_OK
    message = (f"goal-setting: ratify {', '.join(landed)} + scaffold {stubs} downstream "
               "stub/baton path(s) (goal-blitz)")
    try:
        _commit(repo_root, engine_root, paths, message)
    except (CliFailure, Refusal) as exc:
        print(f"land-goals: landed but the scoped commit failed — {exc}", file=sys.stderr)
        for path in paths:
            print(f"    {path}", file=sys.stderr)
        return EXIT_PARTIAL
    print(f"land-goals: committed {len(paths)} path(s).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
