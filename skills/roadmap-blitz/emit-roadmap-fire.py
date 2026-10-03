"""emit-roadmap-fire — collect roadmap-routed sizings, freeze them, and emit bound fire scripts.

Targeted mode (`--sizing <path>`) fires one sizing; sweep mode picks up sizings with
`xl_exit: roadmap` and `status: routed` that have no `state/roadmap/<runId>/` yet. One fire binds
one sizing: each candidate gets `<trail-dir>/<runId>/` holding `candidates.json` (the frozen
candidate plus its bound args, written BEFORE binding) and `roadmap-blitz.fire.mjs`
(`workflow.bind_args` output). A sweep or targeted run also writes `<trail-dir>/candidates.json`,
the index of every candidate and skip. One `Workflow({ scriptPath })` line is printed per fire.

`--resume <trailDir>` re-reads the frozen args, adds `approvalPath`, and re-binds; it refuses an
absent `approval.json`, or one that is not an approved `pm` approval.

`interactionMode` defaults to the sizing's `interaction_mode`. No `approver` is bound here; the
workflow's `approverFor` owns that mapping.

Exit codes: 0 fires emitted; 2 bad input (missing or non-roadmap-routed sizing, invalid runId,
no interaction mode, malformed frozen candidates); 3 sweep found no candidates; 4 bind failed;
5 resume refused (approval.json absent, unreadable, not an approved pm approval).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MODES = ("hands-on", "pm", "ceo")
FIRE_NAME = "roadmap-blitz.fire.mjs"
CANDIDATES_NAME = "candidates.json"
APPROVAL_NAME = "approval.json"
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Refusal(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _scalar(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        if end != -1:
            return raw[1:end]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def top_level_fields(text: str) -> dict[str, str]:
    """Top-level `key: scalar` pairs of a YAML file; nested and block values are ignored."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):(?:\s+(.*))?$", line)
        if m and m.group(2) is not None:
            out.setdefault(m.group(1), _scalar(m.group(2)))
    return out


def _rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def candidate(path: Path, repo_root: Path, fields: dict[str, str]) -> dict:
    return {
        "runId": path.stem,
        "sizing": _rel(path, repo_root),
        "interaction_mode": fields.get("interaction_mode", ""),
        "intent": fields.get("intent") or fields.get("name", ""),
    }


def is_roadmap_routed(fields: dict[str, str]) -> bool:
    return fields.get("xl_exit") == "roadmap" and fields.get("status") == "routed"


def resolve_sizing(repo_root: Path, value: str) -> Path:
    p = Path(value)
    p = p if p.is_absolute() else repo_root / p
    try:
        p.resolve().relative_to(repo_root.resolve())
    except ValueError:
        raise Refusal(2, f"--sizing is outside the repo: {value}")
    if not p.is_file():
        raise Refusal(2, f"--sizing target does not exist: {value}")
    return p


def collect_targeted(repo_root: Path, value: str) -> dict:
    path = resolve_sizing(repo_root, value)
    fields = top_level_fields(path.read_text(encoding="utf-8"))
    if not is_roadmap_routed(fields):
        raise Refusal(
            2,
            f"{value} is not roadmap-routed (need xl_exit: roadmap and status: routed; "
            f"got xl_exit: {fields.get('xl_exit')!r}, status: {fields.get('status')!r})",
        )
    cand = candidate(path, repo_root, fields)
    if not RUN_ID_RE.match(cand["runId"]):
        raise Refusal(2, f"runId {cand['runId']!r} (sizing stem) does not match {RUN_ID_RE.pattern}")
    return cand


def collect_sweep(repo_root: Path) -> tuple[list[dict], list[dict]]:
    """Return (candidates, skipped) over every sizing with xl_exit: roadmap, status: routed."""
    cands: list[dict] = []
    skipped: list[dict] = []
    for path in sorted((repo_root / "state" / "sizings").glob("*.yaml")):
        fields = top_level_fields(path.read_text(encoding="utf-8"))
        if not is_roadmap_routed(fields):
            continue
        cand = candidate(path, repo_root, fields)
        if not RUN_ID_RE.match(cand["runId"]):
            skipped.append({"sizing": cand["sizing"], "reason": "invalid-run-id"})
        elif (repo_root / "state" / "roadmap" / cand["runId"]).exists():
            skipped.append({"sizing": cand["sizing"], "reason": "already-staged"})
        else:
            cands.append(cand)
    return cands, skipped


def settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


def default_invoke() -> Path:
    name = "coordinator-invoke.exe" if os.name == "nt" else "coordinator-invoke"
    return settings_home() / "bin" / name


def bind(invoke: Path, source: Path, args: dict) -> str:
    params = json.dumps({"script_path": str(source), "args": args}, ensure_ascii=False)
    proc = subprocess.run(
        [str(invoke), "workflow.bind_args", "--params-file", "-"],
        input=params,
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        reply = json.loads(proc.stdout)
    except ValueError:
        reply = None
    result = reply.get("result") if isinstance(reply, dict) else None
    if proc.returncode != 0 or not isinstance(result, dict) or not isinstance(result.get("script"), str):
        detail = (proc.stderr or proc.stdout).strip()[:2000]
        raise RuntimeError(f"workflow.bind_args failed (exit {proc.returncode}): {detail}")
    return result["script"]


def _abs_dir(value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        raise argparse.ArgumentTypeError(f"must be an absolute path: {value}")
    return p


def _provision_sidecar_cli(value: str) -> Path:
    p = _abs_dir(value)
    stem = p.name.lower()
    for ext in (".exe", ".py"):
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    if stem != "provision-sidecar":
        raise argparse.ArgumentTypeError(
            f"must be the provision-sidecar CLI, got {p.name!r} (not coordinator-invoke or another CLI): {value}"
        )
    return p


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_args(cand: dict, repo_root: Path, run_dir: Path, mode: str | None, plugin_agents: bool, sidecar_cli: Path | None) -> dict:
    chosen = mode or cand["interaction_mode"]
    if chosen not in MODES:
        raise Refusal(2, f"{cand['sizing']}: interaction mode {chosen!r} is not one of {MODES}; pass --interaction-mode")
    args = {
        "repoRoot": str(repo_root),
        "sizing": cand["sizing"],
        "interactionMode": chosen,
        "trailDir": str(run_dir),
        "runId": cand["runId"],
        "pluginAgentsAvailable": plugin_agents,
    }
    if sidecar_cli is not None:
        args["provisionSidecarCli"] = str(sidecar_cli)
    return args


def _write_receipt(fire: Path, reemit: list[str]) -> None:
    """Land `<fire>.emitted.json` so the Workflow PreToolUse hook sees an emitted, not hand-rolled, fire."""
    path = Path(__file__).resolve().parents[2] / "bin" / "emit-dispatch-workflow.py"
    spec = importlib.util.spec_from_file_location("emit_dispatch_workflow", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._write_emission_receipt(fire, None, receipt_extras={"reemit": reemit})


def emit_fire(invoke: Path, source: Path, run_dir: Path, args: dict, reemit: list[str]) -> str:
    script = bind(invoke, source, args)
    fire = run_dir / FIRE_NAME
    fire.write_text(script, encoding="utf-8")
    _write_receipt(fire, reemit)
    return f"Workflow({{ scriptPath: {json.dumps(str(fire))} }})"


def check_approval(run_dir: Path) -> Path:
    path = run_dir / APPROVAL_NAME
    if not path.is_file():
        raise Refusal(5, f"resume refused: {path} is absent")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Refusal(5, f"resume refused: {path} is not valid JSON: {exc}")
    if not isinstance(doc, dict) or doc.get("approver") != "pm":
        raise Refusal(5, f"resume refused: {path} is not a pm approval (approver: {doc.get('approver') if isinstance(doc, dict) else None!r})")
    if doc.get("verdict") != "approved":
        raise Refusal(5, f"resume refused: {path} verdict is {doc.get('verdict')!r}, not 'approved'")
    return path


def resume(run_dir: Path, invoke: Path, source: Path, reemit: list[str]) -> str:
    cand_path = run_dir / CANDIDATES_NAME
    if not cand_path.is_file():
        raise Refusal(2, f"resume refused: no frozen {cand_path}")
    try:
        frozen = json.loads(cand_path.read_text(encoding="utf-8"))
        args = dict(frozen["candidates"][0]["args"])
    except (ValueError, KeyError, IndexError, TypeError):
        raise Refusal(2, f"resume refused: {cand_path} carries no frozen candidate args")
    approval = check_approval(run_dir)
    args["approvalPath"] = str(approval)
    return emit_fire(invoke, source, run_dir, args, reemit)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-root", required=True, type=_abs_dir)
    ap.add_argument("--trail-dir", required=True, type=_abs_dir, help="base dir for a fire; with --resume, the run's own trailDir")
    ap.add_argument("--sizing", default=None, help="targeted: repo-relative sizing path")
    ap.add_argument("--resume", action="store_true", help="re-bind the frozen args in --trail-dir with approvalPath")
    ap.add_argument("--interaction-mode", choices=MODES, default=None)
    ap.add_argument("--provision-sidecar-cli", type=_provision_sidecar_cli, default=None)
    ap.add_argument("--plugin-root", type=_abs_dir, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--coordinator-invoke", type=_abs_dir, default=None)
    ap.add_argument("--no-plugin-agents", action="store_true")
    ns = ap.parse_args(argv)
    reemit = list(sys.argv[1:] if argv is None else argv)

    repo_root: Path = ns.repo_root
    source = ns.plugin_root / "workflows" / "roadmap-blitz.mjs"
    invoke = ns.coordinator_invoke or default_invoke()
    if not repo_root.is_dir():
        ap.error(f"--repo-root is not a directory: {repo_root}")

    try:
        if ns.resume:
            print(resume(ns.trail_dir, invoke, source, reemit))
            return 0

        if ns.sizing is not None:
            cands, skipped = [collect_targeted(repo_root, ns.sizing)], []
        else:
            cands, skipped = collect_sweep(repo_root)

        mode = "targeted" if ns.sizing is not None else "sweep"
        base: Path = ns.trail_dir
        _write_json(base / CANDIDATES_NAME, {"mode": mode, "candidates": cands, "skipped": skipped})
        for s in skipped:
            print(f"skipped {s['sizing']}: {s['reason']}", file=sys.stderr)
        if not cands:
            print(f"no roadmap-routed sizings to fire; froze empty {base / CANDIDATES_NAME}", file=sys.stderr)
            return 3

        fired = 0
        for cand in cands:
            run_dir = base / cand["runId"]
            try:
                args = build_args(cand, repo_root, run_dir, ns.interaction_mode, not ns.no_plugin_agents, ns.provision_sidecar_cli)
            except Refusal as exc:
                if mode == "targeted":
                    raise
                print(f"skipped {cand['sizing']}: {exc}", file=sys.stderr)
                continue
            _write_json(run_dir / CANDIDATES_NAME, {"mode": mode, "candidates": [{**cand, "args": args}]})
            print(emit_fire(invoke, source, run_dir, args, reemit), flush=True)
            fired += 1
        if not fired:
            print("every candidate was skipped; nothing to fire", file=sys.stderr)
            return 3
        return 0
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
