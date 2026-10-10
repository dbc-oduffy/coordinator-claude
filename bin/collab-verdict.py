"""collab-verdict — read or refresh the per-repo collaboration verdict cache.

`read` prints the cached verdict; `refresh` derives `mode` from commit authorship (never `gh`),
merges it through the monotonic latch, and writes `state/collaboration-verdict.json` atomically.
The on-disk shape is frozen in `coordinator/docs/wiki/collaboration-gate-contract.md`.

INVARIANTS: scope is the coordinator-content-repo checkout this file ships in; `refresh` refuses any other
`repo_root` because only this repo's `.gitignore` ignores the cache. Nothing here prompts or reads
stdin. A corrupt cache fails `refresh` loudly; it is never re-derived as a fresh clone.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

_LIB = Path(__file__).resolve().parent.parent / "lib"

CONTENT_ROOT = Path(__file__).resolve().parents[2]
OVERRIDES = ("solo", "multi", "auto")


class RefreshError(Exception):
    """A refusal `refresh` reports as one stderr line and a non-zero exit."""


def default_probe(repo_root: Path) -> Iterable[str]:
    """Raw author and `Co-authored-by:` emails over HEAD's full history: one `git log` spawn."""
    import collab_detect  # lazy: keeps `read` free of the subprocess-importing module

    return collab_detect.probe_identities(repo_root)


def _frontmatter(repo_root: Path) -> dict:
    path = repo_root / "coordinator.local.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        import yaml

        data = yaml.safe_load(text[3:end])
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_override(repo_root: Path) -> str:
    """`collaboration_mode` from the examined repo's own `coordinator.local.md`; absent or
    unrecognised degrades to `auto`."""
    value = _frontmatter(repo_root).get("collaboration_mode", "auto")
    return value if value in OVERRIDES else "auto"


def read_bot_excludes(repo_root: Path) -> list[str]:
    value = _frontmatter(repo_root).get("collaboration_bot_exclude", [])
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str)]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gate():
    """`collab_gate`, imported on first use so a bare import leaves `sys.path` untouched."""
    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    import collab_gate

    return collab_gate


def _write_atomic(path: Path, verdict: "collab_gate.Verdict") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "mode": verdict.mode,
            "source": verdict.source,
            "author_count": verdict.author_count,
            "checked_at": verdict.checked_at,
        },
        indent=2,
    )
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".collab-verdict.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def refresh(
    repo_root: str | Path,
    *,
    probe: Callable[[Path], Iterable[str]] = default_probe,
    now: Callable[[], str] = _now,
) -> "collab_gate.Verdict":
    """Derive, latch, and persist the verdict for `repo_root`; raise `RefreshError` on refusal.

    `probe` is the injection seam for the one real `git log` spawn.
    """
    root = Path(repo_root).resolve()
    if root != CONTENT_ROOT:
        raise RefreshError(f"refused: {root} is not the coordinator-content-repo checkout this CLI ships in")

    previous = _gate().read_verdict(root)
    if previous.source == "corrupt":
        raise RefreshError(
            f"corrupt cache at {root / _gate().VERDICT_RELPATH}: delete it deliberately to re-derive"
        )

    mode = read_override(root)
    if mode in ("solo", "multi"):
        verdict = _gate().Verdict(
            mode=mode, source="override", author_count=previous.author_count, checked_at=now()
        )
    else:
        import collab_detect

        mailmap_path = root / ".mailmap"
        mailmap = collab_detect.parse_mailmap(mailmap_path) if mailmap_path.exists() else {}
        authors = collab_detect.canonicalize(
            probe(root), mailmap=mailmap, bot_excludes=read_bot_excludes(root)
        )
        observed = _gate().Verdict(
            mode="multi" if len(authors) > 1 else "solo",
            source="detected",
            author_count=len(authors),
            checked_at=now(),
        )
        verdict = collab_detect.merge_verdict(previous, observed)

    _write_atomic(root / _gate().VERDICT_RELPATH, verdict)
    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collab-verdict", description=__doc__.splitlines()[0])
    parser.add_argument("verb", choices=("read", "refresh"))
    parser.add_argument("--repo-root", default=str(CONTENT_ROOT))
    args = parser.parse_args(argv)

    if args.verb == "read":
        v = _gate().read_verdict(args.repo_root)
        print(json.dumps(dataclasses.asdict(v)))
        return 0

    try:
        refresh(args.repo_root)
    except RefreshError as exc:
        print(f"collab-verdict: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
