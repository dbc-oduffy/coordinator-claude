"""emit-goal-fire — collect goal-blitz seeds, freeze them, and emit a bound fire script.

Sweep mode picks up `kind: goal-seed` handoffs parked `deployment_state: awaiting_gate` and
sizings with `route: goal-setting` + `status: sized`. Targeted mode (`--targets`) takes seed
ids (file stems) and reports `unmatched_targets`. The frozen set is written to
`<trailDir>/candidates.json` BEFORE binding, then `workflow.bind_args` binds the args into
`<trailDir>/goal-blitz.fire.mjs`; the last stdout line is the `Workflow({ scriptPath })` call.

`--interaction-mode` is bound as-is. No `approver` is derived here; the workflow's
`ratifierFor` owns that mapping.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MODES = ("hands-on", "pm", "ceo")
FIRE_NAME = "goal-blitz.fire.mjs"
CANDIDATES_NAME = "candidates.json"


def _scalar(raw: str) -> str:
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        if end != -1:
            return raw[1:end]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def top_level_fields(text: str, frontmatter: bool) -> dict[str, str]:
    """Top-level `key: scalar` pairs; nested and block values are ignored."""
    lines = text.splitlines()
    if frontmatter:
        if not lines or lines[0].strip() != "---":
            return {}
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), len(lines))
        lines = lines[1:end]
    out: dict[str, str] = {}
    for line in lines:
        m = re.match(r"^([A-Za-z_][\w-]*):(?:\s+(.*))?$", line)
        if m and m.group(2) is not None:
            out.setdefault(m.group(1), _scalar(m.group(2)))
    return out


def _rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _seed(path: Path, repo_root: Path, kind: str, intent: str) -> dict:
    return {"id": path.stem, "path": _rel(path, repo_root), "kind": kind, "intent": intent}


def collect(repo_root: Path, targets: list[str] | None) -> tuple[list[dict], list[str]]:
    """Return (seeds, unmatched_targets). Sweep when `targets` is None."""
    seeds: list[dict] = []
    wanted = set(targets) if targets is not None else None

    for path in sorted((repo_root / "state" / "handoffs").glob("*.md")):
        if wanted is not None and path.stem not in wanted:
            continue
        f = top_level_fields(path.read_text(encoding="utf-8"), frontmatter=True)
        if f.get("kind") != "goal-seed":
            continue
        if wanted is None and f.get("deployment_state") != "awaiting_gate":
            continue
        seeds.append(_seed(path, repo_root, "goal-seed", f.get("summary") or f.get("title", "")))

    for path in sorted((repo_root / "state" / "sizings").glob("*.yaml")):
        if wanted is not None and path.stem not in wanted:
            continue
        f = top_level_fields(path.read_text(encoding="utf-8"), frontmatter=False)
        if f.get("route") != "goal-setting":
            continue
        if wanted is None and f.get("status") != "sized":
            continue
        seeds.append(_seed(path, repo_root, "sizing", f.get("intent") or f.get("name", "")))

    if wanted is None:
        return seeds, []
    found = {s["id"] for s in seeds}
    return seeds, [t for t in targets if t not in found]


def default_invoke(settings_home: Path) -> Path:
    name = "coordinator-invoke.exe" if os.name == "nt" else "coordinator-invoke"
    return settings_home / "bin" / name


def settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


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
    if proc.returncode != 0 or not isinstance(reply, dict) or "result" not in reply:
        detail = (proc.stderr or proc.stdout).strip()[:2000]
        raise RuntimeError(f"workflow.bind_args failed (exit {proc.returncode}): {detail}")
    return reply["result"]["script"]


def _abs_dir(value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        raise argparse.ArgumentTypeError(f"must be an absolute path: {value}")
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-root", required=True, type=_abs_dir)
    ap.add_argument("--trail-dir", required=True, type=_abs_dir)
    ap.add_argument("--provision-sidecar-cli", required=True, type=_abs_dir)
    ap.add_argument("--interaction-mode", required=True, choices=MODES)
    ap.add_argument("--plugin-root", type=_abs_dir, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--coordinator-invoke", type=_abs_dir, default=None)
    ap.add_argument("--no-plugin-agents", action="store_true")
    ap.add_argument("--targets", nargs="+", metavar="SEED_ID", default=None)
    ns = ap.parse_args(argv)

    repo_root: Path = ns.repo_root
    trail_dir: Path = ns.trail_dir
    source = ns.plugin_root / "workflows" / "goal-blitz.mjs"
    if not repo_root.is_dir():
        ap.error(f"--repo-root is not a directory: {repo_root}")

    seeds, unmatched = collect(repo_root, ns.targets)
    trail_dir.mkdir(parents=True, exist_ok=True)
    (trail_dir / CANDIDATES_NAME).write_text(
        json.dumps(
            {
                "mode": "targeted" if ns.targets is not None else "sweep",
                "seeds": seeds,
                "unmatched_targets": unmatched,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    if unmatched:
        print(f"unmatched_targets: {', '.join(unmatched)}", file=sys.stderr)
    if not seeds:
        print(f"no seeds to fire; froze empty {trail_dir / CANDIDATES_NAME}", file=sys.stderr)
        return 3

    args = {
        "repoRoot": str(repo_root),
        "trailDir": str(trail_dir),
        "provisionSidecarCli": str(ns.provision_sidecar_cli),
        "interactionMode": ns.interaction_mode,
        "pluginAgentsAvailable": not ns.no_plugin_agents,
        "seeds": seeds,
    }
    invoke = ns.coordinator_invoke or default_invoke(settings_home())
    try:
        script = bind(invoke, source, args)
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 4

    fire = trail_dir / FIRE_NAME
    fire.write_text(script, encoding="utf-8")
    print(f"Workflow({{ scriptPath: {json.dumps(str(fire))} }})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
