"""session-start-index-freshness.py -- async SessionStart leg: assess the repo's project-rag index
freshness and cache the verdict.

Folded into `sessionstart-async-dispatch.py` (sources startup|resume). Calls the installed
project-rag CLI and parses its JSON only (contract: schema_version 1; project_rag_core is never
imported): `freshness-verdict --repo <slug>` (local files and git, no network). On a `stale` or `absent`
verdict, or when no verdict was obtained, it then fires `refresh-from-release --stale-only --repo
<slug>` once: the harness fires it, never an agent, under the ruling in
`docs/decisions/DR-freshness-leg-refresh-from-release.md`. The verb enforces its own admission, so
there is no hook-side throttle and any outcome, including `skipped:min_gap`, is accepted. It pulls a published bundle and rolls forward incrementally;
it never embeds and never builds from scratch. `current` and `unknown` start nothing.

Cache: `<repo>/.coordinator-local/index-freshness-verdict.json`, read (never recomputed) by the
sync PROJECT-RAG-FIRST banner and by the sweep skills' preconditions
(`coordinator/skill-preconditions.yaml`). `unknown`, a `current` row carrying a reason, a verdict
outside the closed set, or a schema_version other than 1 reads as not current.

Absent project-rag, an unregistered repo or any failure: return 0 silently (SessionStart never
blocks). Tests inject `_run`; nothing here shells out at import.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from _win_portability import no_console_spawn_kwargs  # noqa: E402

CACHE_REL = Path(".coordinator-local") / "index-freshness-verdict.json"
CACHE_VERSION = 1
SCHEMA_VERSION = 1
VERDICTS = frozenset({"current", "stale", "absent", "unknown"})
CLI_ENV = "PROJECT_RAG_CLI"
CLI_REGISTRY_KEY = "project_rag.bin.project_rag_cli"
#: The verdict is one repo of local git work (the CLI's own per-repo budget is 6 s); this bounds the
#: leg inside the async fan-in's shared 15 s.
VERDICT_TIMEOUT_S = 10
#: Verdicts that fire the refresh; `current` and `unknown` never do.
REFRESH_VERDICTS = frozenset({"stale", "absent"})


def _now() -> float:
    return time.time()


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(argv: list, cwd: str, timeout: float) -> Optional[tuple]:
    """(returncode, stdout, stderr) or None when the process could not run or timed out."""
    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, **no_console_spawn_kwargs())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return proc.returncode, proc.stdout, proc.stderr


def _registry_pairs() -> dict:
    """Flattened machine-local registry (local layer over tracked baseline); {} when unreadable."""
    try:
        import tomllib
        from _engine_root import _flatten_registry, _settings_home_registry_dir
        reg_dir = _settings_home_registry_dir()
    except Exception:
        return {}
    merged: dict = {}
    for name in ("registry.toml", "registry.local.toml"):
        try:
            with (reg_dir / name).open("rb") as fh:
                merged.update(_flatten_registry(tomllib.load(fh)))
        except Exception:
            continue
    return merged


def resolve_cli(registry: Optional[dict] = None) -> Optional[list]:
    """The installed project-rag CLI as an argv prefix, or None when project-rag is not installed.
    Order: `$PROJECT_RAG_CLI`, the registered `project_rag.bin.project_rag_cli` file, then PATH."""
    reg = _registry_pairs() if registry is None else registry
    candidates = [os.environ.get(CLI_ENV), reg.get(CLI_REGISTRY_KEY), shutil.which("project-rag-cli")]
    for cand in candidates:
        if isinstance(cand, str) and cand and Path(cand).expanduser().is_file():
            path = str(Path(cand).expanduser())
            return [sys.executable, path] if path.endswith(".py") else [path]
    return None


def resolve_slug(root: Path, registry: Optional[dict] = None) -> Optional[str]:
    """The registered `repos.<slug>` whose path is `root`.

    Several keys can alias one path (a tooling alias beside the canonical key). The canonical slug
    is the root's basename with `-` as `_`; project-rag indexes under that one, so an alias must
    never win by sort order. Several matches and none canonical: None, never a guess.
    """
    from _engine_root import _same_repo_path
    reg = _registry_pairs() if registry is None else registry
    matches = [
        key[len("repos."):]
        for key in sorted(k for k in reg if k.startswith("repos.") and k.count(".") == 1)
        if isinstance(reg[key], str) and reg[key] and _same_repo_path(reg[key], str(root))
    ]
    # Registry keys are lowercase; a mixed-case basename must still match its key.
    canonical = Path(root).name.replace("-", "_").lower()
    if canonical in matches:
        return canonical
    return matches[0] if len(matches) == 1 else None


def effective_row(reply: Any, slug: str) -> dict:
    """The verdict row for slug, normalised. Anything the contract does not vouch for reads `unknown`."""
    bad = {"verdict": "unknown", "reason": "unparseable_reply", "remedy": {"action": "none", "argv": []}}
    if not isinstance(reply, dict):
        return bad
    if reply.get("schema_version") != SCHEMA_VERSION:
        return {**bad, "reason": "schema_version_mismatch"}
    rows = reply.get("repos")
    if not isinstance(rows, list):
        return bad
    row = next((r for r in rows if isinstance(r, dict) and r.get("slug") == slug), None)
    if row is None:
        row = next((r for r in rows if isinstance(r, dict)), None) if len(rows) == 1 else None
    if row is None:
        return {**bad, "reason": "no_row_for_slug"}
    out = dict(row)
    if out.get("verdict") not in VERDICTS or (out["verdict"] == "current" and out.get("reason") is not None):
        out["verdict"] = "unknown"
    if not isinstance(out.get("remedy"), dict):
        out["remedy"] = {"action": "none", "argv": []}
    return out


def read_cache(root: Path) -> Optional[dict]:
    try:
        data = json.loads((root / CACHE_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("cache_version") == CACHE_VERSION else None


def write_cache(root: Path, slug: str, row: dict, checked_epoch: Optional[float] = None) -> None:
    epoch = _now() if checked_epoch is None else checked_epoch
    body = {
        "cache_version": CACHE_VERSION, "schema_version": SCHEMA_VERSION, "slug": slug,
        "checked_at": _iso(epoch), "checked_epoch": epoch,
        "verdict": row.get("verdict"), "reason": row.get("reason"), "row": row,
    }
    dest = root / CACHE_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, dest)


def assess(cli: list, slug: str, root: Path) -> Optional[dict]:
    """Run the verdict and return its normalised row; None when the CLI did not run to an exit 0."""
    result = _run([*cli, "freshness-verdict", "--repo", slug], str(root), VERDICT_TIMEOUT_S)
    if result is None or result[0] != 0:
        return None
    try:
        reply = json.loads(result[1])
    except ValueError:
        reply = None
    return effective_row(reply, slug)


def _spawn_detached(argv: list, cwd: str) -> None:
    """Start argv in its own session and return at once; a failure to start is swallowed.

    Trap: the async legs run serially under one 45 s registration timeout and sweep_boot runs last
    on its own 30 s, so a pull awaited here would starve sweep_boot. The leg never waits on it.
    """
    hidden = no_console_spawn_kwargs()
    flags = (hidden.pop("creationflags", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
             | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, start_new_session=os.name != "nt", close_fds=True, **hidden)
    except (OSError, ValueError):
        pass


def refresh(cli: list, slug: str, root: Path) -> None:
    """Fire the pull-first refresh once, detached. The outcome is not read: the verb throttles itself."""
    _spawn_detached([*cli, "refresh-from-release", "--stale-only", "--repo", slug], str(root))


def _boot(root: Path) -> int:
    registry = _registry_pairs()
    cli = resolve_cli(registry)
    if cli is None:
        return 0
    slug = resolve_slug(root, registry)
    if slug is None:
        return 0
    row = assess(cli, slug, root)
    if row is not None:
        write_cache(root, slug, row)
    if row is None or row.get("verdict") in REFRESH_VERDICTS:
        refresh(cli, slug, root)
    return 0


def main(argv: Optional[list] = None) -> int:
    try:
        from _engine_root import _session_repo_root
        root = _session_repo_root()
        if root is None:
            return 0
        return _boot(root)
    except Exception:  # SessionStart never blocks
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
